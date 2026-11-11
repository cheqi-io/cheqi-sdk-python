"""Keep OAuth diagnostics redacted after every model regeneration."""
from pathlib import Path
import re

models = Path(__file__).resolve().parent.parent / "src/cheqi/models/generated"
for path in models.glob("*.py"):
    source = path.read_text()
    sensitive = {"client_secret", "access_token", "refresh_token", "id_token", "code_verifier"}
    if path.stem == "authorization_code_exchange_request":
        sensitive.add("code")
    fields = sorted(name for name in sensitive if re.search(r"^    " + name + r":", source, re.M))
    if not fields:
        continue
    if "Field" not in re.search(r"from pydantic import (.*)", source).group(1).split(", "):
        source = source.replace("from pydantic import ", "from pydantic import Field, ", 1)
    for name in fields:
        source = re.sub(r"(^    " + name + r": [^\n]+ = )None$", r"\1Field(default=None, repr=False)", source, flags=re.M)
        source = re.sub(r"(^    " + name + r": [^\n]+ = Field\()(?![^\n]*repr=)", r"\1repr=False, ", source, flags=re.M)
    if "hide_input_in_errors=True" not in source:
        source = source.replace("        protected_namespaces=(),", "        protected_namespaces=(),\n        hide_input_in_errors=True,")
    source = source.replace("return pprint.pformat(self.model_dump(by_alias=True))",
                            "return pprint.pformat({key: '<redacted>' if key in " + repr(tuple(fields)) +
                            " else value for key, value in self.model_dump(by_alias=True).items()})")
    # to_dict / to_json are explicit wire serialization APIs and retain credentials.
    path.write_text(source)
