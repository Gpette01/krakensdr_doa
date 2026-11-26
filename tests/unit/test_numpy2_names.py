# NumPy 2.0 removed several aliases; the repo's own code must not use them (finding D-44, T-16).
import re

from conftest import REPO_ROOT

REMOVED_NAMES = (
    "Infinity infty Inf PINF NINF NaN NAN NZERO PZERO float_ complex_ cfloat longfloat singlecomplex clongfloat "
    "longcomplex string_ unicode_ round_ alltrue sometrue product cumproduct asfarray issubclass_ find_common_type "
    "safe_eval mat set_string_function fastCopyAndTranspose"
).split()
PATTERN = re.compile(r"\bnp\.(" + "|".join(REMOVED_NAMES) + r")\b")
SOURCE_DIRS = ("_sdr", "_ui", "benchmarks", "tests")


def test_no_numpy_name_removed_in_numpy_2():
    found = []
    for directory in SOURCE_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            if path.name == "test_numpy2_names.py":
                continue
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                if PATTERN.search(line):
                    found.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}")
    assert found == []
