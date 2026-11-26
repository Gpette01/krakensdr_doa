# Custom array text cases shared by the load-path tests (follow-up to M1-06).
VALID_X = "0.21,0.06,-0.17,-0.17,0.07"
VALID_Y = "0.0,-0.2,-0.12,0.12,0.2"

# name -> (x text, y text); only "valid" may be accepted.
CASES = {
    "valid": (VALID_X, VALID_Y),
    "0 coordinates": ("", ""),
    "1 coordinate": ("0.1", "0.1"),
    "4 coordinates": ("0.1,0.2,0.3,0.4", "0.1,0.2,0.3,0.4"),
    "6 coordinates": ("0.1,0.2,0.3,0.4,0.5,0.6", "0.1,0.2,0.3,0.4,0.5,0.6"),
    "20 coordinates": (",".join(["0.1"] * 20), ",".join(["0.1"] * 20)),
    "non-numeric": ("a,b,c,d,e", "a,b,c,d,e"),
    "trailing comma": (VALID_X + ",", VALID_Y + ","),
    "x and y counts differ": (VALID_X, "0.1,0.2,0.3,0.4"),
}
