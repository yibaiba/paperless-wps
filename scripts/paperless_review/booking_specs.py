"""Explicit V2.2 rows reviewed for booking; never infer identity from model alone."""

from dataclasses import dataclass

SHEET = "会议预约与信发系统"
ACTOR = "会议预约配套复核（2026-10-04）"
MARKER = "【会议预约配套复核20261004】"
PACKAGE = "28b513aa-c06b-448d-aedd-afc5090f0733"
DEFINITION = "e401b647-18ee-42b0-9f9f-120628e5b1b9"
MODELS = {
    6: "CRIR-FC20S",
    7: "CRIR-CL1",
    8: "CRIR-D-EM",
    9: "CRIR-D-IN",
    10: "CRIR-D-SM",
    11: "CRIR-D-WE",
    12: "CRIR-D-DD",
    13: "CRIR-D-OA",
    14: "CRIR-D-CC",
    15: "CRIR-D-EG",
    17: "CRIR-1516N",
    18: "CRIR-GL20S",
    19: "CRIR-KA20S",
    21: "CSIS-B101YD",
    22: "CSIS-B156YD",
    23: "CSIS-B215YD",
}


@dataclass(frozen=True)
class Mapping:
    identity: str
    revision: int
    row: int
    old_role: str
    role_id: str
    quote: str


MAPPINGS = (
    Mapping(
        "cd7e5e13-83a6-4866-8584-56bb471e0236",
        2,
        17,
        "服务端",
        "server",
        "操作系统：支持Linux操作系统",
    ),
    Mapping(
        "e00ce321-f3ab-46e4-b793-361f22bff304",
        1,
        21,
        "预约显示终端",
        "terminal",
        "操作系统：Android 11",
    ),
    Mapping(
        "ecade75d-d1a9-4c89-b83e-682a98b12f44",
        1,
        22,
        "预约显示终端",
        "terminal",
        "操作系统：Android 11",
    ),
    Mapping(
        "fecb3046-52d1-4d13-90a4-8ccd94acf6b5",
        1,
        23,
        "预约显示终端",
        "terminal",
        "21.5不支持POE供电",
    ),
)


@dataclass(frozen=True)
class Accessory:
    identity: str
    revision: int
    key: str
    source_rows: tuple[int, ...]
    target_row: int
    quote: str = ""


ACCESSORIES = (
    Accessory(
        "06893fd2-5fb9-4222-9acd-ef6aec7e0b78",
        2,
        "display-terminal-software",
        (21, 22, 23),
        19,
        "每个显示终端一套",
    ),
    Accessory(
        "bd3efe41-949b-50d0-8ed8-ff74879ac3f7",
        1,
        "face-terminal-license",
        (6,),
        7,
        "每个签到终端需发放一个授权",
    ),
    Accessory("033887ec-73d7-5485-aeb7-affbc922f1f2", 1, "server-hardware", (18,), 17),
    Accessory("2f416475-2ee9-5bdd-b8bc-3cdcaff77810", 1, "integration.email", (18,), 8),
    Accessory("9c7037e8-c66c-53d7-8cfc-215457e12f12", 1, "integration.sso", (18,), 9),
    Accessory("6b0313c5-d909-5de5-9df4-73962a4a1710", 1, "integration.sms", (18,), 10),
    Accessory("09c02fb0-ae25-5d09-981f-0a9f74980e38", 1, "integration.wecom", (18,), 11),
    Accessory("9466963b-b93a-5f28-ba60-c0fad32d504a", 1, "integration.dingtalk", (18,), 12),
    Accessory("db5977e3-7aec-51e0-98e7-a8390723f173", 1, "integration.oa", (18,), 13),
    Accessory("0198c3f5-27fd-5dee-aed9-4b58e0af8f31", 1, "integration.control", (18,), 14),
    Accessory("81fd2226-a1a0-5c9d-9af1-c95a3aa3ce91", 1, "integration.access", (18,), 15),
)
