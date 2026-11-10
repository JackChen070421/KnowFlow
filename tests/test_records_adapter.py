"""Synthetic-only regression tests; no official record content."""

import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from knowflow.io.records_adapter import (
    COLUMNS, ConversionError, convert_rows, load_id_map, read_csv, write_new_json,
    extract_details, DETAIL_COLUMNS, validate_rows,
)


class RecordsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.row = dict.fromkeys(COLUMNS, "")
        self.row.update({"记录编号": "demo-r", "学生编号": "demo-s", "材料编号": "Q001",
                         "评分状态": "已评分", "得分": "2", "满分": "3", "修订版本": "1",
                         "模拟提交时间": "2026-11-10T10:00:00+08:00", "学生最终作答": "synthetic"})
        self.mapping = {"version": 1, "records": {"demo-r": "R-0001", "demo-r2": "R-0002"},
                        "students": {"demo-s": "S001"}, "materials": {"Q001": "M-001"}}

    def convert(self, **updates):
        return convert_rows([{**self.row, **updates}], self.mapping)[0]

    def test_partial_score_and_private_default(self):
        row = self.convert()
        self.assertEqual(row["score"], 2)
        self.assertFalse(row["is_correct"])
        self.assertIsNone(row["answer"])
        self.assertIsNone(row["duration_seconds"])

    def test_pending_and_unattempted_are_distinct(self):
        pending = self.convert(评分状态="待评分", 得分="")
        absent = self.convert(评分状态="未作答", 得分="")
        self.assertTrue(pending["attempted"])
        self.assertFalse(absent["attempted"])
        for row in [pending, absent]:
            self.assertTrue(row["assigned"])
            self.assertIsNone(row["score"])
            self.assertIsNone(row["is_correct"])

    def test_score_validation(self):
        for score in ["", "NaN", "Infinity", "-1", "4", "text"]:
            with self.subTest(score=score), self.assertRaises(ConversionError):
                self.convert(得分=score)
        with self.assertRaises(ConversionError):
            self.convert(评分状态="待评分", 得分="0")

    def test_status_revision_and_timezone_validation(self):
        for updates in [{"评分状态": "unknown"}, {"修订版本": "0"},
                        {"模拟提交时间": "2026-11-10T10:00:00"},
                        {"模拟提交时间": "2026-99-10T10:00:00+08:00"}]:
            with self.subTest(updates=updates), self.assertRaises(ConversionError):
                self.convert(**updates)

    def test_unknown_and_duplicate_ids_rejected(self):
        with self.assertRaises(ConversionError):
            self.convert(材料编号="Q999")
        with self.assertRaises(ConversionError):
            convert_rows([self.row, self.row], self.mapping)

    def test_revisions_retained_and_subset_id_stable(self):
        revised = {**self.row, "记录编号": "demo-r2", "修订版本": "2"}
        all_rows = convert_rows([self.row, revised], self.mapping)
        subset = convert_rows([revised], self.mapping)
        self.assertEqual(len(all_rows), 2)
        self.assertEqual(all_rows[1], subset[0])
        self.assertEqual(subset[0]["record_id"], "R-0002")

    def test_map_collision_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map.json"
            mapping = copy.deepcopy(self.mapping)
            mapping["records"]["demo-r2"] = "R-0001"
            path.write_text(json.dumps(mapping), encoding="utf-8")
            with self.assertRaises(ConversionError):
                load_id_map(path)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            write_new_json(path, [1])
            with self.assertRaises(FileExistsError):
                write_new_json(path, [2])
            self.assertEqual(json.loads(path.read_text()), [1])

    def test_unknown_header_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "in.csv"
            path.write_text("wrong\nvalue\n", encoding="utf-8")
            with self.assertRaises(ConversionError):
                read_csv(path)

    def test_detail_text_preserved_and_schema_valid(self):
        row = {**self.row, "解答过程": "  第一行\n第二行：x=2  ", "评分点得分": '{"P1":0,"P2":1}'}
        detail = extract_details(row, self.convert(), 4)
        self.assertEqual(detail["solution_process"], row["解答过程"])
        self.assertEqual(detail["scoring_point_scores"], row["评分点得分"])
        self.assertEqual(detail["final_answer"], "synthetic")
        validate_rows([detail], Path(__file__).resolve().parents[1] / "schemas/input/record_details.schema.json")

    def test_missing_empty_whitespace_and_zero_details(self):
        for value in [None, "", " \n\t"]:
            row = {**self.row, **dict.fromkeys(DETAIL_COLUMNS, value)}
            detail = extract_details(row, self.convert(), 2)
            for field in ["final_answer", "solution_process", "scoring_point_scores"]:
                self.assertEqual(detail[field], "NULL")
        detail = extract_details({**self.row, "评分点得分": "0"}, self.convert(), 2)
        self.assertEqual(detail["scoring_point_scores"], "0")

    def test_optional_detail_columns_can_be_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "without_details.csv"
            fields = [key for key in COLUMNS if key not in DETAIL_COLUMNS]
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({key: self.row[key] for key in fields})
            row = read_csv(path)[0]
            detail = extract_details(row, convert_rows([row], self.mapping)[0], 2)
            self.assertEqual(detail["solution_process"], "NULL")
            self.assertEqual(detail["scoring_point_scores"], "NULL")


if __name__ == "__main__":
    unittest.main()
