"""AI 광고 상담(/consults)과 게시 문구 변환(/copies/convert). api_spec_consult 3·4장.

이미지 생성(GPU 대기열)과 상관없는 텍스트 호출이라 대기열에 넣지 않는다. 대신
- 하루 횟수: 상담 시작은 client 3회·IP 10회, 변환은 client 20회 (설정값, DB 기준이라 재시작해도 유지)
- 금액: OpenAI를 쓰면 이미지와 같은 하루 상한에 더하고, 텍스트는 상한의 consult_budget_share까지만.
  넘으면 로컬 Gemma로 바꾸고 응답 source="local"
- OpenAI가 실패하면 Gemma로 한 번 더 (그것도 실패하면 503)
- Gemma는 klein과 GPU를 나눠 쓰므로 텍스트 호출은 동시에 1개만
- 상담에서 사장님이 직접 쓴 글은 OpenAI Moderation(무료)으로 먼저 거름 (칩은 거르지 않음)

모델 호출은 TextModels로 감싸 테스트·mock 모드에서 바꿔 끼운다.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod

from .generators import GeneratorError
from .queue_manager import DailyLimitError, QueueManager, run_with_deadline
from .records import GenerationRecords
from .settings import ServingSettings

logger = logging.getLogger(__name__)

REPLY_OFF_TOPIC = (
    "그 부분은 제가 도와드리기 어려워요. 대신 이번 광고 이야기를 이어 갈게요. "
)
REPLY_OFF_TOPIC_BRIEF = (
    "그 부분은 제가 도와드리기 어려워요. 기획서에서 바꾸고 싶은 점을 적어 주세요."
)
REPLY_END = (
    "광고 이야기가 아니라서 상담을 여기서 마칠게요. 바로 만들기는 언제든 쓸 수 있어요."
)
REPLY_BRIEF = (
    "정리했어요! 아래 내용으로 바로 만들 수 있어요. 바꾸고 싶은 게 있으면 적어 주세요."
)
REPLY_EDITED = "고쳐서 다시 정리했어요."
MAX_OFF_TOPIC = 3  # 같은 상담에서 연속 3번 주제 밖이면 종료
BRIEF_EDITS = 2  # 기획서를 고칠 수 있는 횟수 (terra 호출)


class ConsultNotFoundError(LookupError):
    """없는 상담 또는 다른 사람의 상담 (404)."""


class ConsultEndedError(RuntimeError):
    """이미 끝난 상담 (409)."""


class ModerationError(ValueError):
    """Moderation에 걸린 글 (400)."""


# ---------------------------------------------------------------------- 모델
class TextModels(ABC):
    """상담·변환에 쓰는 모델 호출. 반환 dict에는 source·model·cost_usd가 들어간다."""

    @abstractmethod
    def read_answer(
        self, slot: str, question: str, text: str, answers: dict, quality: str
    ) -> dict:
        """{"off_topic", "filled", "source", "model", "cost_usd"}"""

    @abstractmethod
    def write_brief(
        self,
        answers: dict,
        purpose_hint: str | None,
        previous: dict | None,
        tweak: str | None,
        quality: str,
    ) -> dict:
        """{"off_topic", "brief", "source", "model", "cost_usd"}"""

    @abstractmethod
    def convert(
        self,
        text: str,
        fmt: str,
        product_name: str | None,
        area: str | None,
        facts: dict | None,
        quality: str,
    ) -> dict:
        """{"result", "fixed_typos", "source", "model", "cost_usd"}"""

    @abstractmethod
    def moderate(self, text: str) -> bool:
        """걸리면 True."""


def _wrap(fn, *args):
    """core 오류를 서빙 오류로: 입력 오류는 ValueError 그대로, 모델 오류는 GeneratorError."""
    from just_make_it.core.base import TextGenerationError

    try:
        return fn(*args)
    except ValueError:
        raise
    except TextGenerationError as exc:
        raise GeneratorError(str(exc)) from exc
    except Exception as exc:  # 키 누락 등
        raise GeneratorError(f"{type(exc).__name__}: {exc}") from exc


class CoreTextModels(TextModels):
    def read_answer(self, slot, question, text, answers, quality):
        from just_make_it.core.consultant import read_answer

        off, filled, res = _wrap(read_answer, slot, question, text, answers, quality)
        return {
            "off_topic": off,
            "filled": filled,
            "source": res.source,
            "model": res.model,
            "cost_usd": res.cost_usd,
        }

    def write_brief(self, answers, purpose_hint, previous, tweak, quality):
        from just_make_it.core.consultant import write_brief

        off, brief, res = _wrap(
            write_brief, answers, purpose_hint, previous, tweak, quality
        )
        return {
            "off_topic": off,
            "brief": brief,
            "source": res.source,
            "model": res.model,
            "cost_usd": res.cost_usd,
        }

    def convert(self, text, fmt, product_name, area, facts, quality):
        from just_make_it.core.copy_convert import convert_copy

        return _wrap(convert_copy, text, fmt, product_name, area, facts, quality)

    def moderate(self, text):
        from just_make_it.core.structured import moderate

        return moderate(text)


class MockTextModels(TextModels):
    """API 키·GPU 없이 개발·테스트용. 프론트 lib/mock.ts와 같은 흐름."""

    OFF_TOPIC = re.compile(r"숙제|코딩|주식|코인|대출|세금|시스템 프롬프트")
    FLAGGED = re.compile(r"MODERATION_TEST")

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []  # (어떤 호출, 품질)

    def _check(self, what, quality):
        self.calls.append((what, quality))
        if self.fail and quality != "basic":
            raise GeneratorError("mock OpenAI 실패")

    def read_answer(self, slot, question, text, answers, quality):
        self._check("read_answer", quality)
        off = bool(self.OFF_TOPIC.search(text))
        return {
            "off_topic": off,
            "filled": {} if off else {slot: text.strip()},
            "source": "local" if quality == "basic" else "openai",
            "model": "mock",
            "cost_usd": 0.0 if quality == "basic" else 0.0002,
        }

    def write_brief(self, answers, purpose_hint, previous, tweak, quality):
        from just_make_it.core.consultant import purpose_for

        self._check("write_brief", quality)
        if tweak and self.OFF_TOPIC.search(tweak):
            return {
                "off_topic": True,
                "brief": previous,
                "source": "openai",
                "model": "mock",
                "cost_usd": 0.01,
            }
        product = answers.get("product_name", "")
        strengths = (
            []
            if answers.get("strengths") == "모르겠어요"
            else [answers.get("strengths", "")]
        )
        channel = answers.get("channel", "인스타그램")
        if channel == "잘 모르겠어요":
            channel = "인스타그램"
        brief = {
            "category": answers.get("category", ""),
            "goal": answers.get("goal", ""),
            "product_name": product,
            "period": (
                None
                if answers.get("period") in (None, "", "기간 없어요")
                else answers["period"]
            ),
            "strengths": [s for s in strengths if s],
            "audience": answers.get("audience", ""),
            "purpose": purpose_for(channel, purpose_hint),
            "channel": channel,
            "message": f"{answers.get('audience', '')}이 먼저 찾는 {product}",
            "copies": [
                tweak or f"{answers.get('goal', '')}! {product}",
                f"정성 가득 {product}",
            ],
            "style": "따뜻한",
            "reason": "손님이 좋아하는 점을 앞에 두었어요.",
            "next_tips": [],
        }
        return {
            "off_topic": False,
            "brief": brief,
            "source": "local" if quality == "basic" else "openai",
            "model": "mock",
            "cost_usd": 0.0 if quality == "basic" else 0.01,
        }

    def convert(self, text, fmt, product_name, area, facts, quality):
        self._check("convert", quality)
        product = product_name or "우리 가게"
        results = {
            "instagram_post": f"{text}\n\n오늘도 {product} 준비했어요.",
            "instagram_hashtags": [f"#{product.replace(' ', '')}", "#동네가게"],
            "instagram_location": [area, f"{area} 근처"] if area else [],
            "instagram_story": text[:15],
            "naver_coupon": {
                "title": text,
                "condition": (facts or {}).get("discount", "조건을 적어 주세요"),
                "period": (facts or {}).get("until", "기간을 적어 주세요"),
            },
            "naver_blog_title": [
                f"{product}, {text}",
                f"요즘 {product}",
                f"{text} 이야기",
            ],
            "store_description": f"{product}\n\n{text}",
        }
        return {
            "result": results[fmt],
            "fixed_typos": False,
            "source": "local" if quality == "basic" else "openai",
            "model": "mock",
            "cost_usd": 0.0 if quality == "basic" else 0.0005,
        }

    def moderate(self, text):
        return bool(self.FLAGGED.search(text))


# ---------------------------------------------------------------------- 서비스
class AssistantService:
    def __init__(
        self,
        settings: ServingSettings,
        manager: QueueManager,
        records: GenerationRecords,
        models: TextModels,
    ) -> None:
        self.settings = settings
        self.manager = manager
        self.records = records
        self.models = models
        # 로컬 Gemma는 klein과 GPU를 나눠 쓰므로 텍스트 호출은 동시에 1개
        self._local_slot = asyncio.Semaphore(1)

    # ------------------------------------------------------------------ 모델 호출
    async def _call(self, method, *args, quality: str):
        """금액 몫이 남아 있으면 OpenAI(quality), 아니면 Gemma. OpenAI가 실패하면 Gemma로 한 번 더."""
        chosen = quality if self.manager.text_api_allowed else "basic"
        try:
            return await self._run(method, *args, chosen)
        except (GeneratorError, TimeoutError) as exc:
            if chosen == "basic":
                raise GeneratorError(str(exc)) from exc
            logger.warning("텍스트 OpenAI 실패 → Gemma로 다시: %s", exc)
            return await self._run(method, *args, "basic")

    async def _run(self, method, *args):
        quality = args[-1]
        timeout = self.settings.text_task_timeout_seconds
        if quality == "basic":
            async with self._local_slot:
                return await run_with_deadline(method, *args, timeout=timeout)
        return await run_with_deadline(method, *args, timeout=timeout)

    async def _spend(self, kind, client_id, ip, result):
        cost = float(result.get("cost_usd") or 0.0)
        self.manager.add_text_cost(cost)
        await asyncio.to_thread(
            self.records.add_text_call,
            kind,
            client_id,
            ip,
            model=result.get("model"),
            source=result.get("source"),
            cost_usd=cost,
        )

    # ------------------------------------------------------------------ 상담
    async def start_consult(self, client_id: str, ip: str | None, start: dict) -> dict:
        """첫 질문은 고정 문구 (모델 호출 없음, 비용 0)."""
        from just_make_it.core.consultant import first_question

        s = self.settings
        if (
            s.consult_daily_limit
            and await asyncio.to_thread(
                self.records.count_text_calls, "consult_start", client_id=client_id
            )
            >= s.consult_daily_limit
        ):
            raise DailyLimitError("상담 하루 횟수 초과 (client)")
        if (
            ip
            and s.consult_ip_daily_limit
            and await asyncio.to_thread(
                self.records.count_text_calls, "consult_start", ip=ip
            )
            >= s.consult_ip_daily_limit
        ):
            raise DailyLimitError("상담 하루 횟수 초과 (IP)")

        _, question, chips = first_question(start.get("product_name"))
        cid = await asyncio.to_thread(
            self.records.start_consult,
            client_id,
            ip,
            start,
            {"role": "assistant", "text": question, "chips": chips},
        )
        await asyncio.to_thread(
            self.records.add_text_call, "consult_start", client_id, ip, source="none"
        )
        return self._turn(await self._get(cid, client_id), question, chips, None)

    async def get_consult(self, cid: str, client_id: str) -> dict:
        c = await self._get(cid, client_id)
        return {
            "id": c["id"],
            "messages": c["messages"],
            "brief": c["brief"],
            "ended": c["ended"],
            "edits_left": c["edits_left"],
        }

    async def send(
        self, cid: str, client_id: str, ip: str | None, text: str, chip: bool
    ) -> dict:
        from just_make_it.core.consultant import next_question

        c = await self._get(cid, client_id)
        if c["ended"] or c["turn"] >= self.settings.consult_max_turns:
            raise ConsultEndedError(cid)
        text = text.strip()
        if not chip and await asyncio.to_thread(self.models.moderate, text):
            # 턴은 세지만 모델은 부르지 않고, 글도 남기지 않음 (원문 저장 안 함)
            c["turn"] += 1
            await asyncio.to_thread(self.records.save_consult, c)
            logger.warning("상담 Moderation 걸림 consult=%s", cid)
            raise ModerationError(cid)

        start = c["start"]
        answers = c["answers"]
        source = None
        if c["brief"] is None:
            slot, question, chips = next_question(answers, start.get("product_name"))
            off = False
            if chip:
                answers[slot] = text
            else:
                res = await self._call(
                    self.models.read_answer,
                    slot,
                    question,
                    text,
                    dict(answers),
                    quality="natural",
                )
                await self._spend("consult_turn", client_id, ip, res)
                source = res["source"]
                off = res["off_topic"]
                if not off:
                    answers.update(res["filled"])
            if off:
                reply, chips = self._off_topic(c, REPLY_OFF_TOPIC + question, chips)
            else:
                c["off_topic"] = 0
                nxt = next_question(answers, start.get("product_name"))
                if nxt:
                    _, reply, chips = nxt
                else:
                    res = await self._call(
                        self.models.write_brief,
                        dict(answers),
                        start.get("purpose"),
                        None,
                        None,
                        quality="terra",
                    )
                    await self._spend("consult_turn", client_id, ip, res)
                    source = res["source"]
                    c["brief"] = res["brief"]
                    c["edits_left"] = BRIEF_EDITS
                    reply, chips = REPLY_BRIEF, []
        else:
            if not c["edits_left"]:
                raise ConsultEndedError(cid)
            res = await self._call(
                self.models.write_brief,
                dict(answers),
                start.get("purpose"),
                c["brief"],
                text,
                quality="terra",
            )
            await self._spend("consult_turn", client_id, ip, res)
            source = res["source"]
            if res["off_topic"]:
                reply, chips = self._off_topic(c, REPLY_OFF_TOPIC_BRIEF, [])
            else:
                c["off_topic"] = 0
                c["brief"] = res["brief"]
                c["edits_left"] -= 1
                reply, chips = REPLY_EDITED, []
                if c["edits_left"] == 0:
                    c["ended"] = True

        c["turn"] += 1
        c["messages"].append({"role": "user", "text": text})
        c["messages"].append({"role": "assistant", "text": reply, "chips": chips})
        await asyncio.to_thread(self.records.save_consult, c)
        return self._turn(c, reply, chips, source)

    def _off_topic(self, c: dict, reply: str, chips: list) -> tuple[str, list]:
        c["off_topic"] += 1
        if c["off_topic"] >= MAX_OFF_TOPIC:
            c["ended"] = True
            return REPLY_END, []
        return reply, chips

    async def _get(self, cid: str, client_id: str) -> dict:
        c = await asyncio.to_thread(self.records.get_consult, cid)
        # 만든 사람만 볼 수 있음 (다르면 없는 것처럼 404)
        if c is None or c["client_id"] != client_id:
            raise ConsultNotFoundError(cid)
        return c

    def _turn(self, c: dict, reply: str, chips: list, source: str | None) -> dict:
        ended = c["ended"] or c["turn"] >= self.settings.consult_max_turns
        return {
            "id": c["id"],
            "reply": reply,
            "chips": [] if ended else chips,
            "allow_free_text": not ended,
            "turn": c["turn"],
            "max_turns": self.settings.consult_max_turns,
            "brief": c["brief"],
            "ended": ended,
            "edits_left": c["edits_left"],
            "source": source,
        }

    # ------------------------------------------------------------------ 문구 변환
    async def convert(
        self,
        client_id: str,
        ip: str | None,
        text: str,
        fmt: str,
        product_name: str | None,
        area: str | None,
        facts: dict | None,
    ) -> dict:
        limit = self.settings.convert_daily_limit
        if (
            limit
            and await asyncio.to_thread(
                self.records.count_text_calls, "convert", client_id=client_id
            )
            >= limit
        ):
            raise DailyLimitError("문구 변환 하루 횟수 초과")
        res = await self._call(
            self.models.convert,
            text,
            fmt,
            product_name,
            area,
            facts,
            quality="natural",
        )
        await self._spend("convert", client_id, ip, res)
        return {
            "format": fmt,
            "result": res["result"],
            "fixed_typos": bool(res.get("fixed_typos")),
            "source": res["source"],
        }
