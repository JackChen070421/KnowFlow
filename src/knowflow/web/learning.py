"""Student-owned formative learning, persisted separately from official diagnosis."""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from knowflow.config import get_settings
from knowflow.llm.client import LLMError, OpenAICompatClient
from knowflow.web.learning_math import grade_answer
from knowflow.web.learning_probes import PROBES


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, TypeError) as exc:
        raise ValueError("AI 返回格式不完整，请重试。") from exc


class LearningStore:
    def __init__(self, root: Path, snapshot: dict, knowledge: dict):
        self.root, self.snapshot, self.knowledge = root, snapshot, knowledge
        self.lock = threading.RLock()
        self.generating = set()

    def check_owner(self, student_id, node_id):
        if not isinstance(student_id, str) or not isinstance(node_id, str):
            raise ValueError("学生或测验编号无效。")
        if student_id not in {s["student_id"] for s in self.snapshot["students"]}:
            raise ValueError("没有找到该学生。")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", student_id):
            raise ValueError("学生编号无效。")
        if student_id not in self.snapshot["profiles"].get(node_id, {}):
            raise ValueError("当前测验没有该学生的画像。")

    def _material(self, mid):
        return next((m for m in self.knowledge["materials"] if m["material_id"] == mid), None)

    def _from_material(self, mid, kid=None):
        m = self._material(mid)
        if (
            not m
            or m.get("material_type") not in ("assessment", "practice", "probe")
            or not m.get("body")
        ):
            raise ValueError("该材料没有可练习的题目。")
        mappings = [
            q
            for q in self.knowledge["qmatrix"]
            if q["material_id"] == mid and q.get("weight", 0) > 0
        ]
        kid = kid or next((q["knowledge_id"] for q in mappings), None)
        if not kid:
            raise ValueError("题目尚未关联知识点。")
        try:
            options = json.loads(m.get("options_json") or "[]")
        except (ValueError, TypeError):
            options = []
        if not isinstance(options, list) or len(options) != 4:
            options = []
        options = [re.sub(r"^[A-D][.、．：:]\s*", "", str(o)) for o in options]
        return {
            "question_id": mid,
            "knowledge_id": kid,
            "prompt": m["body"],
            "options": options,
            "answer": m.get("answer_key") or "",
            "explanation": m.get("explanation") or "",
            "material_id": mid,
            "source": "bank",
            "source_label": "题库原题",
            "source_note": m.get("source") or "课程题库",
        }

    def _load(self, sid):
        path = self.root / (sid + ".json")
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                raise ValueError("学习记录无法读取，请联系教师检查本机文件。") from exc
        else:
            data = {
                "schema_version": "1.0.0",
                "student_id": sid,
                "lessons": {},
                "questions": {},
                "attempts": [],
                "mistakes": {},
                "favorites": [],
                "revealed": [],
            }
        # Seed historical loss-of-credit questions without inventing new answers.
        for r in self.snapshot["records"]:
            if r["student_id"] != sid or r.get("score") is None or not r.get("attempted"):
                continue
            if r["score"] >= r.get("max_score", 0):
                continue
            mid = r["material_id"]
            if mid in data["mistakes"]:
                continue
            try:
                q = self._from_material(mid)
            except ValueError:
                continue
            data["questions"].setdefault(mid, q)
            data["mistakes"][mid] = {
                "question_id": mid,
                "resolved": False,
                "origin": "history",
                "node_id": r["node_id"],
                "record_id": r["record_id"],
                "score": r["score"],
                "max_score": r["max_score"],
                "created_at": now(),
            }
        return data

    def _save(self, data):
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / (data["student_id"] + ".json")
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, target)

    def _state(self, sid, nid, kid):
        state = next(
            (
                s
                for s in self.snapshot["profiles"][nid][sid]["knowledge_states"]
                if s["knowledge_id"] == kid
            ),
            None,
        )
        if not state or state["status"] == "not_applicable":
            raise ValueError("该知识点不属于当前学习范围。")
        return state

    @staticmethod
    def _key(nid, kid):
        return nid + ":" + kid

    @staticmethod
    def _public(q, data):
        result = {k: v for k, v in q.items() if k not in ("answer", "explanation")}
        result["favorite"] = q["question_id"] in data["favorites"]
        result["attempt"] = next(
            (a for a in reversed(data["attempts"]) if a["question_id"] == q["question_id"]), None
        )
        return result

    def _overview(self, kid):
        graph = self.knowledge.get("curriculum_graph") or {}
        nodes = [n for n in graph.get("nodes", []) if kid in n.get("knowledge_ids", [])]
        selected = {n["node_id"] for n in nodes}
        links = []
        for e in graph.get("edges", []):
            if e["source_node_id"] in selected or e["target_node_id"] in selected:
                links.append(e)
        summaries = [
            {
                "title": n["title"],
                "text": n["summary"],
                "node_id": n["node_id"],
                "source_locator": n.get("source_locator"),
                "document_url": self._material(n.get("material_id"))
                and self._material(n["material_id"]).get("document_url"),
                "pdf_page": n.get("pdf_page", 1),
            }
            for n in nodes
        ]
        if not summaries:
            knowledge = next(k for k in self.knowledge["knowledge"] if k["knowledge_id"] == kid)
            summaries = [
                {
                    "title": knowledge["name"],
                    "text": knowledge.get("description")
                    or "先梳理概念与解题步骤，再通过练习检查理解。",
                }
            ]
        return {
            "sections": summaries,
            "edges": links,
            "focus": nodes[0]["node_id"] if nodes else kid,
        }

    def list_for(self, sid, nid):
        self.check_owner(sid, nid)
        with self.lock:
            data = self._load(sid)
            names = {k["knowledge_id"]: k["name"] for k in self.knowledge["knowledge"]}
            cards = []
            for s in self.snapshot["profiles"][nid][sid]["knowledge_states"]:
                if s["status"] == "not_applicable":
                    continue
                kid = s["knowledge_id"]
                lesson = data["lessons"].get(self._key(nid, kid), {})
                probe = lesson.get("probe_result")
                mode = (
                    "probe" if s["status"] in ("unobserved", "insufficient_evidence") else "learn"
                )
                if probe:
                    mode = "learn"
                status = probe["status"] if probe else s["status"]
                cards.append(
                    {
                        "knowledge_id": kid,
                        "name": names.get(kid, kid),
                        "mode": mode,
                        "status": status,
                        "evidence_count": s.get("evidence_count", 0),
                        "probe_result": probe,
                        "read": lesson.get("read", False),
                        "started": bool(lesson),
                        "completed": lesson.get("completed", False),
                    }
                )
            order = {"probe": 0, "learn": 1}
            cards.sort(
                key=lambda c: (
                    order[c["mode"]],
                    c["status"]
                    not in ("confirmed_weak", "likely_weak", "needs_practice", "mixed_performance"),
                    c["knowledge_id"],
                )
            )
            mistakes = []
            for qid, m in data["mistakes"].items():
                if qid in data["questions"]:
                    mistakes.append({**self._public(data["questions"][qid], data), **m})
            favorites = [
                self._public(data["questions"][qid], data)
                for qid in data["favorites"]
                if qid in data["questions"]
            ]
            self._save(data)
            settings = get_settings()
            return {
                "cards": cards,
                "mistakes": mistakes,
                "favorites": favorites,
                "ai_ready": settings.llm_ready,
                "ai_model": settings.llm_model,
                "names": names,
            }

    def _session(self, data, nid, kid):
        lesson = data["lessons"][self._key(nid, kid)]
        return {
            **copy.deepcopy(lesson),
            "knowledge_id": kid,
            "overview": self._overview(kid),
            "probe_questions": [
                self._public(data["questions"][q], data) for q in lesson.get("probe_ids", [])
            ],
            "bank_questions": [
                self._public(data["questions"][q], data) for q in lesson["bank_ids"]
            ],
            "ai_questions": [self._public(data["questions"][q], data) for q in lesson["ai_ids"]],
        }

    def start(self, sid, nid, kid):
        self.check_owner(sid, nid)
        state = self._state(sid, nid, kid)
        with self.lock:
            data = self._load(sid)
            key = self._key(nid, kid)
            if key not in data["lessons"]:
                candidates = []
                for mapping in self.knowledge["qmatrix"]:
                    if mapping["knowledge_id"] != kid or mapping.get("weight", 0) <= 0:
                        continue
                    try:
                        q = self._from_material(mapping["material_id"], kid)
                    except ValueError:
                        continue
                    candidates.append(q)
                # Prefer concise exercises with deterministic grading, then retain source order.
                candidates.sort(key=lambda q: (not bool(q["options"]), len(q["prompt"])))
                unique = {q["question_id"]: q for q in candidates}
                bank = list(unique.values())[:2]
                for q in bank:
                    data["questions"].setdefault(q["question_id"], q)
                lesson = {
                    "read": False,
                    "completed": False,
                    "bank_ids": [q["question_id"] for q in bank],
                    "ai_ids": [],
                    "created_at": now(),
                    "probe_ids": [],
                    "probe_result": None,
                }
                if state["status"] in ("unobserved", "insufficient_evidence"):
                    if kid not in PROBES:
                        raise ValueError("该知识点暂未配置可靠的两题补测，请联系教师。")
                    lesson["probe_id"] = str(uuid.uuid4())
                    for prompt, options, answer, explanation in PROBES[kid]:
                        qid = "P-" + str(uuid.uuid4())
                        data["questions"][qid] = {
                            "question_id": qid,
                            "knowledge_id": kid,
                            "prompt": prompt,
                            "options": options,
                            "answer": answer,
                            "explanation": explanation,
                            "source": "probe",
                            "source_label": "基础补测",
                            "source_note": "本机编写的形成性检查题",
                            "probe_id": lesson["probe_id"],
                        }
                        lesson["probe_ids"].append(qid)
                data["lessons"][key] = lesson
                self._save(data)
            return self._session(data, nid, kid)

    def mark_read(self, sid, nid, kid):
        self.check_owner(sid, nid)
        with self.lock:
            data = self._load(sid)
            lesson = data["lessons"].get(self._key(nid, kid))
            if not lesson:
                raise ValueError("请先打开学习卡。")
            if lesson["probe_ids"] and not lesson["probe_result"]:
                raise ValueError("请先完成两题补测。")
            lesson["read"] = True
            self._save(data)
            return self._session(data, nid, kid)

    def question(self, sid, nid, qid):
        self.check_owner(sid, nid)
        with self.lock:
            data = self._load(sid)
            if qid not in data["questions"]:
                data["questions"][qid] = self._from_material(qid)
            q = data["questions"][qid]
            out = self._public(q, data)
            if out["attempt"] or qid in data["mistakes"]:
                out["solution"] = {"answer": q["answer"], "explanation": q["explanation"]}
            self._save(data)
            return out

    def favorite(self, sid, nid, qid, value):
        if type(value) is not bool:
            raise ValueError("收藏状态无效。")
        self.check_owner(sid, nid)
        with self.lock:
            data = self._load(sid)
            if qid not in data["questions"]:
                data["questions"][qid] = self._from_material(qid)
            if value and qid not in data["favorites"]:
                data["favorites"].append(qid)
            if not value:
                data["favorites"] = [x for x in data["favorites"] if x != qid]
            self._save(data)
            return {"favorite": value}

    def answer(self, sid, nid, payload):
        self.check_owner(sid, nid)
        qid = payload.get("question_id")
        answer = payload.get("answer")
        rid = payload.get("request_id")
        if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 1000:
            raise ValueError("请填写 1–1000 字的答案。")
        if not isinstance(rid, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", rid):
            raise ValueError("请求编号无效。")
        with self.lock:
            data = self._load(sid)
            old = next((a for a in data["attempts"] if a["request_id"] == rid), None)
            if old:
                if old["question_id"] != qid or old["answer"] != answer.strip():
                    raise ValueError("请勿重复使用作答编号。")
                return copy.deepcopy(old)
            q = data["questions"].get(qid)
            if not q:
                raise ValueError("请先打开该题目。")
            correct = grade_answer(q, answer)
            lesson = data["lessons"].get(self._key(nid, q["knowledge_id"]))
            if q.get("source") == "probe" and (not lesson or qid not in lesson["probe_ids"]):
                raise ValueError("补测不属于当前测验。")
            independent = (
                not any(a["question_id"] == qid for a in data["attempts"])
                and qid not in data["mistakes"]
            )
            attempt = {
                "request_id": rid,
                "question_id": qid,
                "answer": answer.strip(),
                "correct": correct,
                "node_id": nid,
                "knowledge_id": q["knowledge_id"],
                "independent": independent,
                "created_at": now(),
                "reference_answer": q["answer"],
                "explanation": q["explanation"],
            }
            data["attempts"].append(attempt)
            if correct is False:
                data["mistakes"].setdefault(
                    qid,
                    {"question_id": qid, "origin": "practice", "created_at": now(), "node_id": nid},
                )
                data["mistakes"][qid]["resolved"] = False
            elif correct is True and qid in data["mistakes"]:
                data["mistakes"][qid]["resolved"] = True
                data["mistakes"][qid]["resolved_at"] = now()
            if lesson and lesson["probe_ids"] and not lesson["probe_result"]:
                first = [
                    next(
                        (
                            a
                            for a in data["attempts"]
                            if a["question_id"] == p and type(a["correct"]) is bool
                        ),
                        None,
                    )
                    for p in lesson["probe_ids"]
                ]
                if all(first):
                    score = sum(a["correct"] for a in first)
                    lesson["probe_result"] = {
                        "correct": score,
                        "total": 2,
                        "accuracy": score / 2,
                        "status": "needs_practice" if score <= 1 else "ready",
                        "created_at": now(),
                    }
            if lesson:
                required = lesson["bank_ids"] + lesson["ai_ids"][-2:]
                attempted = {a["question_id"] for a in data["attempts"]}
                lesson["completed"] = bool(
                    lesson["read"] and lesson["ai_ids"] and set(required) <= attempted
                )
                attempt["probe_result"] = copy.deepcopy(lesson.get("probe_result"))
            self._save(data)
            return copy.deepcopy(attempt)

    def generate(self, sid, nid, kid, client=None):
        self.check_owner(sid, nid)
        state = self._state(sid, nid, kid)
        flight = (sid, nid, kid)
        with self.lock:
            data = self._load(sid)
            lesson = data["lessons"].get(self._key(nid, kid))
            if not lesson or not lesson["read"]:
                raise ValueError("先完成知识阅读，再开始 AI 变式。")
            attempted = {a["question_id"] for a in data["attempts"]}
            if not set(lesson["bank_ids"] + lesson["ai_ids"][-2:]) <= attempted:
                raise ValueError("请先完成当前练习，再生成下一组。")
            if flight in self.generating:
                raise ValueError("正在出题，请稍候。")
            previous = [data["questions"][q]["prompt"] for q in lesson["ai_ids"][-12:]]
            self.generating.add(flight)
        try:
            settings = get_settings()
            if client is None:
                if not settings.llm_ready:
                    raise ValueError("AI 尚未配置，请让教师在设置中连接模型。")
                client = OpenAICompatClient(
                    provider=settings.llm_provider,
                    model=settings.llm_model,
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    temperature=0.25,
                    timeout=max(30, settings.llm_timeout_seconds),
                    max_tokens=1900,
                    json_mode=True,
                )
            name = next(k["name"] for k in self.knowledge["knowledge"] if k["knowledge_id"] == kid)
            summary = {
                "knowledge": name,
                "objectives": [s["text"] for s in self._overview(kid)["sections"]],
                "level": "进阶变式"
                if state["status"] in ("confirmed_mastered", "likely_mastered")
                else "基础巩固",
                "count": 2,
                "avoid_questions": previous,
            }
            for attempt_number in range(2):
                try:
                    raw = client.complete(
                        '你是七年级数学出题教师。只返回 JSON：{"questions":[{"prompt":"题干",'
                        '"options":["选项A","选项B","选项C","选项D"],"answer":"A","explanation":"具体推导"}]}。'
                        "生成恰好2道不同的新题；每题四个不同选项且仅一个正确选项。答案仅 A/B/C/D。"
                        "不要在题干或选项标注正确答案；选项不带字母前缀。使用纯文本数学符号，不用 LaTeX。"
                        "题目自包含，无图片，无需外部材料。解析必须说明计算或推理。",
                        json.dumps(summary, ensure_ascii=False),
                    )
                    questions = parse_json(raw).get("questions")
                    if not isinstance(questions, list) or len(questions) != 2:
                        raise ValueError("AI 未返回两道完整题目，请重试。")
                    seen = set(previous)
                    for q in questions:
                        if not isinstance(q, dict) or not all(
                            isinstance(q.get(k), str) and 1 <= len(q[k]) <= 1400
                            for k in ("prompt", "answer", "explanation")
                        ):
                            raise ValueError("AI 题目字段不完整，请重试。")
                        if (
                            q["answer"] not in ("A", "B", "C", "D")
                            or not isinstance(q.get("options"), list)
                            or len(q["options"]) != 4
                        ):
                            raise ValueError("AI 题目选项不完整，请重试。")
                        if (
                            not all(isinstance(x, str) and 1 <= len(x) <= 400 for x in q["options"])
                            or len(set(q["options"])) != 4
                            or q["prompt"] in seen
                        ):
                            raise ValueError("AI 生成了重复题目或选项，请重试。")
                        seen.add(q["prompt"])
                    # A second request does not receive the generator's proposed answers.
                    reviewed = parse_json(
                        client.complete(
                            "独立核对两道七年级数学单选题。只返回 JSON："
                            '{"answers":["A","B"]}。选项依次对应 ABCD。逐题计算；无唯一正确项则返回 ?。',
                            json.dumps(
                                {
                                    "questions": [
                                        {"prompt": q["prompt"], "options": q["options"]}
                                        for q in questions
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        )
                    )
                    if reviewed.get("answers") != [q["answer"] for q in questions]:
                        raise ValueError("这组题的答案复核未通过，未加入练习。请重新生成。")
                    break
                except ValueError:
                    if attempt_number == 1:
                        raise
            with self.lock:
                data = self._load(sid)
                lesson = data["lessons"][self._key(nid, kid)]
                for q in questions:
                    qid = "AI-" + str(uuid.uuid4())
                    data["questions"][qid] = {
                        **q,
                        "question_id": qid,
                        "knowledge_id": kid,
                        "source": "ai",
                        "source_label": "AI 变式",
                        "source_note": "模型生成并经独立请求复核",
                        "model": getattr(client, "model", "test"),
                        "generated_at": now(),
                        "verified": True,
                    }
                    lesson["ai_ids"].append(qid)
                lesson["completed"] = False
                self._save(data)
                return self._session(data, nid, kid)
        except LLMError as exc:
            labels = {
                "auth": "API Key 无效",
                "billing": "API 余额不足",
                "timeout": "AI 响应超时",
                "network": "无法连接 AI 服务",
                "rate_limit": "调用过于频繁",
            }
            raise ValueError(
                labels.get(exc.kind, "AI 服务暂不可用") + "，请稍后重试或联系教师检查设置。"
            ) from None
        finally:
            with self.lock:
                self.generating.discard(flight)
