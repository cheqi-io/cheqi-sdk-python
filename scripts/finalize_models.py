"""Preserve backend decimal fields and use Pydantic JSON serialization."""

import ast
import sys
from pathlib import Path

import yaml

schemas = yaml.safe_load(Path("openapi.yaml").read_text())["components"]["schemas"]
for path in Path(sys.argv[1]).glob("*.py"):
    source = path.read_text()
    lines = source.splitlines(keepends=True)
    decimal_fields = False
    for model in ast.parse(source).body:
        if not isinstance(model, ast.ClassDef):
            continue
        properties = schemas.get(model.name, {}).get("properties", {})
        for field in model.body:
            if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name):
                continue
            alias = field.target.id
            if isinstance(field.value, ast.Call):
                for keyword in field.value.keywords:
                    if keyword.arg == "alias" and isinstance(keyword.value, ast.Constant):
                        alias = keyword.value.value
            if properties.get(alias, {}).get("format") == "decimal":
                index = field.lineno - 1
                if "Union[StrictFloat, StrictInt]" not in lines[index]:
                    raise ValueError(f"Unexpected generated decimal annotation: {path}:{field.lineno}")
                lines[index] = lines[index].replace("Union[StrictFloat, StrictInt]", "Decimal")
                decimal_fields = True
    source = "".join(lines)
    if decimal_fields:
        source = source.replace("import pprint", "from decimal import Decimal\nimport pprint", 1)
    source = source.replace("return json.dumps(self.to_dict())",
                            "return self.model_dump_json(by_alias=True, exclude_none=True)")
    source = source.replace("return cls.from_dict(json.loads(json_str))",
                            "return cls.model_validate_json(json_str)")
    source = source.replace(
        "        # TODO: pydantic v2: use .model_dump_json(by_alias=True, exclude_unset=True) instead\n", ""
    )
    path.write_text(source)
