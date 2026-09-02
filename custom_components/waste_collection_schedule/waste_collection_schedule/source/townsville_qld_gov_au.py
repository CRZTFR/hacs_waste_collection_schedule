import re
from datetime import datetime

import requests
from waste_collection_schedule import Collection, Icons  # type: ignore[attr-defined]
from waste_collection_schedule.exceptions import (
    SourceArgAmbiguousWithSuggestions,
    SourceArgumentExceptionMultiple,
    SourceArgumentNotFound,
    SourceArgumentNotFoundWithSuggestions,
)

TITLE = "Townsville"
DESCRIPTION = "Source for Townsville."
URL = "https://townsville.qld.gov.au/"
TEST_CASES = {
    "Woodwark Drive, Bushland Beach": {
        "property_id": "009fe2d01b9ba090598520202d4bcbc7"
    },
    "Riverway Dr, Kelso": {"property_id": "d41fe69c1b5ba090598520202d4bcb3c"},
    "37 Pilkington St, Garbutt": {"property_id": "580f6e5c1b5ba090598520202d4bcb91"},
    "37 Pilkington Street, Garbutt (address lookup)": {
        "address": "37 Pilkington Street",
        "suburb": "Garbutt",
    },
}


ICON_MAP = {
    "Rubbish": Icons.GENERAL_WASTE,
    "Recycle": Icons.RECYCLING,
}


API_URL = "https://mitownsville.service-now.com/api/cio19/bin_collection_dates/getBinCollectionCal"
SEARCH_API_URL = "https://mitownsville.service-now.com/api/cio19/bin_collection_dates/searchBinCollectionDates"


def _address_label(result: dict) -> str:
    unit = str(result.get("u_unit_number") or "").strip()
    number = str(result.get("u_house_number") or "").strip()
    suffix = str(result.get("u_house_number_suffix") or "").strip()
    number_to = str(result.get("u_house_number_to") or "").strip()
    street = str(result.get("u_street") or "").strip()
    prefix = f"{unit}/" if unit and unit != "0" else ""
    house = f"{number}{suffix}"
    if number_to and number_to != "0":
        house += f"-{number_to}"
    return f"{prefix}{house} {street}".strip()


def _normalise_address(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.lower()))


class Source:
    def __init__(
        self,
        property_id: str | None = None,
        address: str | None = None,
        suburb: str | None = None,
    ):
        self._property_id = str(property_id).strip() if property_id else None
        self._address = " ".join((address or "").replace(",", " ").split())
        self._suburb = " ".join((suburb or "").split())

        if not self._property_id and (not self._address or not self._suburb):
            missing = []
            if not self._address:
                missing.append("address")
            if not self._suburb:
                missing.append("suburb")
            raise SourceArgumentExceptionMultiple(
                missing,
                "specify property_id or both address and suburb",
            )

    def _resolve_property_id(self) -> str:
        match = re.fullmatch(
            r"(?:(?P<unit>[A-Za-z0-9-]+)\s*/\s*)?"
            r"(?P<number>\d+)(?P<suffix>[A-Za-z]?)"
            r"(?:\s*-\s*(?P<number_to>\d+)[A-Za-z]?)?\s+"
            r"(?P<street>.+)",
            self._address,
        )
        if not match:
            raise SourceArgumentNotFound("address", self._address)

        query = [f"u_house_number={match.group('number')}"]
        if match.group("suffix"):
            query.append(f"u_house_number_suffix={match.group('suffix')}")
        if match.group("number_to"):
            query.append(f"u_house_number_to={match.group('number_to')}")
        if match.group("unit"):
            query.append(f"u_unit_number={match.group('unit')}")
        query.extend(
            (
                f"u_streetLIKE{match.group('street')}",
                f"u_localityLIKE{self._suburb}",
            )
        )

        response = requests.get(
            SEARCH_API_URL,
            params={"query": "^".join(query)},
        )
        response.raise_for_status()
        results = response.json().get("result") or []
        if not results:
            raise SourceArgumentNotFound("address", self._address)

        wanted = _normalise_address(self._address)
        exact = [r for r in results if _normalise_address(_address_label(r)) == wanted]
        if len(exact) == 1:
            return str(exact[0]["sys_id"])

        suggestions = [_address_label(result) for result in results]
        if len(results) == 1:
            raise SourceArgumentNotFoundWithSuggestions(
                "address", self._address, suggestions
            )
        raise SourceArgAmbiguousWithSuggestions(
            "address",
            self._address,
            suggestions,
        )

    def fetch(self) -> list[Collection]:
        if not self._property_id:
            self._property_id = self._resolve_property_id()

        params = {"p_id": self._property_id}

        r = requests.get(API_URL, params=params)
        r.raise_for_status()
        data = r.json()

        entries = []
        for d in data["result"]:
            bin_type = d["title"]
            # date format like: 2024-01-03T00:00:00+00:00
            date = datetime.strptime(d["start"], "%Y-%m-%dT%H:%M:%S%z").date()
            icon = ICON_MAP.get(bin_type)  # Collection icon
            entries.append(Collection(date=date, t=bin_type, icon=icon))

        return entries
