"""CLI: official 作答记录.csv -> schema-validated canonical JSON array."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from knowflow.io.records_adapter import (  # noqa: E402
    ConversionError, convert_rows, initialize_id_map, load_id_map,
    read_csv, validate_rows, write_new_json, extract_details,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="不调用LLM，将官方作答CSV转换为canonical JSON数组")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--details-output", type=Path, help="明细JSON；默认在主输出旁生成 <文件名>_details.json")
    parser.add_argument("--id-map", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=ROOT / "schemas/input/records.schema.json")
    parser.add_argument("--init-id-map", action="store_true", help="仅首次运行，从完整登记表生成编号映射")
    parser.add_argument("--materials", type=Path)
    parser.add_argument("--students", type=Path)
    parser.add_argument("--include-answer", action="store_true", help="显式保存最终作答，仅限本机；默认不保存")
    parser.add_argument("--skip-invalid", action="store_true", help="跳过异常记录并保存核查清单，不修改原始值")
    parser.add_argument("--issues-output", type=Path, help="配合 --skip-invalid，单独保存异常位置及原因")
    args = parser.parse_args(argv)
    details_output = args.details_output or args.output.with_name(args.output.stem + "_details.json")
    details_schema = ROOT / "schemas/input/record_details.schema.json"
    try:
        protected = [args.source, args.id_map, args.schema, details_schema, args.materials, args.students]
        if details_output.exists() or any(
            details_output.resolve() == p.resolve()
            for p in [args.output, *protected] if p is not None
        ):
            raise ConversionError("明细输出已存在或与输入、主输出、映射、schema路径冲突")
        if any(p is not None and args.output.resolve() == p.resolve() for p in protected):
            raise ConversionError("输出文件不能与输入、schema或映射文件相同")
        if args.output.exists():
            raise ConversionError("输出文件已存在，请使用新文件名，避免覆盖")
        if args.skip_invalid:
            if not args.issues_output:
                raise ConversionError("--skip-invalid 必须提供 --issues-output")
            if args.issues_output.exists() or any(
                args.issues_output.resolve() == p.resolve()
                for p in [args.output, details_output, *protected] if p is not None
            ):
                raise ConversionError("核查清单路径已存在或与其他文件冲突")
        if not args.schema.is_file():
            raise ConversionError("找不到records.schema.json，请指定 --schema")
        if not details_schema.is_file():
            raise ConversionError("找不到schemas/input/record_details.schema.json")
        rows = read_csv(args.source)
        if args.init_id_map:
            if not args.materials or not args.students:
                raise ConversionError("初始化编号需要 --materials 和 --students 完整登记表")
            initialize_id_map(rows, args.materials, args.students, args.id_map)
        mapping = load_id_map(args.id_map)
        issues, details = [], []
        if args.skip_invalid:
            records, seen = [], set()
            for line, row in enumerate(rows, 2):
                try:
                    record = convert_rows([row], mapping, args.include_answer)[0]
                    if record["record_id"] in seen:
                        raise ConversionError("记录主键重复")
                    seen.add(record["record_id"])
                    records.append(record)
                    details.append(extract_details(row, record, line))
                except ConversionError as exc:
                    issues.append({"csv_record_number": line,
                                   "reason": str(exc).removeprefix("第2行：")})
        else:
            records = convert_rows(rows, mapping, args.include_answer)
            details = [extract_details(row, record, line)
                       for line, (row, record) in enumerate(zip(rows, records), 2)]
        validate_rows(records, args.schema)
        validate_rows(details, details_schema)
        if args.skip_invalid:
            write_new_json(args.issues_output, {
                "input_records": len(rows), "exported_records": len(records),
                "rejected_records": len(issues), "issues": issues,
                "note": "行号按CSV逻辑记录计数，表头为1；异常未自动修改，原始数据保留。",
            })
        write_new_json(details_output, details)
        write_new_json(args.output, records)
        print(f"EXPORT OK records={len(records)} output={args.output} details={details_output}")
        return 0
    except (ConversionError, OSError, ValueError, ImportError) as exc:
        # Never print row data or raw answers in logs.
        message = str(exc) if isinstance(exc, ConversionError) else type(exc).__name__
        print(f"EXPORT FAILED: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
