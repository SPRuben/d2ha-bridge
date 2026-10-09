# -*- coding: utf-8 -*-
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class DovitEvent:
    dev_id: int
    statetype: int
    statevalue_raw: str

def extract_hidv_state(xml_text: str) -> Optional[DovitEvent]:
    if "<hidv-state" not in xml_text:
        return None

    root = ET.fromstring(xml_text)
    if root.tag != "hidv-state":
        return None

    dev = root.find("device")
    if dev is None:
        return None

    dev_id_str = dev.get("id")
    st = dev.findtext("statetype")
    sv = dev.findtext("statevalue")

    if dev_id_str is None or st is None or sv is None:
        return None

    return DovitEvent(
        dev_id=int(dev_id_str),
        statetype=int(st),
        statevalue_raw=str(sv).strip(),
    )