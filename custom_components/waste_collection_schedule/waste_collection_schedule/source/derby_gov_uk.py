import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from waste_collection_schedule import Collection, Icons  # type: ignore[attr-defined]
from waste_collection_schedule.exceptions import (
    SourceArgAmbiguousWithSuggestions,
    SourceArgumentExceptionMultiple,
    SourceArgumentNotFound,
    SourceArgumentNotFoundWithSuggestions,
)

TITLE = "Derby City Council"
DESCRIPTION = "Source for Derby.gov.uk services for Derby City Council, UK."
URL = "https://derby.gov.uk"
TEST_CASES = {
    # Derby City council wants specific addresses, and they can't
    # be business addresses. Hopefully these are suitably generic..
    "22A Wood Road, Chaddesden, Derby, DE21 4LU": {
        # The flat above Bargain Hut on Wood Road
        "premises_id": "10010688168"
    },
    "Allestree Home Improvements, 512 Duffield Road, Derby, DE22 2DL": {
        "premises_id": "100030310335"
    },
    "22A Wood Road via postcode": {
        "postcode": "DE21 4LU",
        "address": "22A Wood Road",
    },
}

ICON_MAP = {
    "Black bin": Icons.GENERAL_WASTE,
    "Blue bin": Icons.RECYCLING,
    "Brown bin": Icons.BIO_KITCHEN,
}

_LOGGER = logging.getLogger(__name__)


PARAM_TRANSLATIONS = {
    "en": {
        "premises_id": "Premises ID",
        "postcode": "Postcode",
        "address": "Address",
        "post_code": "DEPRECATED: post_code",
        "house_number": "DEPRECATED: house_number",
    }
}

PARAM_DESCRIPTIONS = {
    "en": {
        "premises_id": "The number after /BinDays/ on Derby's bin-day result page.",
        "postcode": "Postcode used to retrieve Derby's property list.",
        "address": "The address to select from the postcode's property list.",
        "post_code": "LEAVE EMPTY; retained for existing configurations.",
        "house_number": "LEAVE EMPTY; retained for existing configurations.",
    }
}

HOW_TO_GET_ARGUMENTS_DESCRIPTION = {
    "en": "Either enter a postcode and address, or search on <https://secure.derby.gov.uk/binday> and use the number after `/BinDays/` as the premises ID.",
}

SEARCH_URL = "https://secure.derby.gov.uk/binday"


def _address_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.lower()))


class Source:
    def __init__(
        self,
        premises_id: int | None = None,
        postcode: str | None = None,
        address: str | None = None,
        post_code: str | None = None,
        house_number: str | None = None,
    ):
        self._premises_id = str(premises_id).strip() if premises_id else None
        self._postcode = "".join((postcode or "").split()).upper()
        self._address = " ".join((address or "").split())
        if not self._premises_id and (not self._postcode or not self._address):
            missing = []
            if not self._postcode:
                missing.append("postcode")
            if not self._address:
                missing.append("address")
            raise SourceArgumentExceptionMultiple(
                missing,
                "specify premises_id or both postcode and address",
            )
        self._session = requests.Session()

    def _resolve_premises_id(self) -> str:
        response = self._session.get(SEARCH_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, features="html.parser")
        token = soup.select_one('input[name="__RequestVerificationToken"]')
        if token is None or not token.get("value"):
            raise ValueError("Unable to read Derby's address search form")

        response = self._session.post(
            SEARCH_URL,
            data={
                "Postcode": self._postcode,
                "__RequestVerificationToken": token["value"],
            },
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, features="html.parser")
        candidates = [
            (option.get_text(" ", strip=True), str(option.get("value")))
            for option in soup.select('select[name="SelectedUprn"] option[value]')
            if option.get("value")
        ]
        if not candidates:
            raise SourceArgumentNotFound("postcode", self._postcode)

        wanted = _address_tokens(self._address)
        exact = [item for item in candidates if _address_tokens(item[0]) == wanted]
        if len(exact) == 1:
            return exact[0][1]

        prefix = [
            item
            for item in candidates
            if _address_tokens(item[0])[: len(wanted)] == wanted
        ]
        if len(prefix) == 1:
            return prefix[0][1]
        if len(prefix) > 1:
            raise SourceArgAmbiguousWithSuggestions(
                "address", self._address, [label for label, _ in prefix]
            )
        raise SourceArgumentNotFoundWithSuggestions(
            "address", self._address, [label for label, _ in candidates]
        )

    def fetch(self):
        if not self._premises_id:
            self._premises_id = self._resolve_premises_id()

        entries = []
        r = self._session.get(
            f"https://secure.derby.gov.uk/binday/Bindays/{self._premises_id}"
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, features="html.parser")
        results = soup.find_all("div", {"class": "binresult"})

        for result in results:
            date = result.find("strong")
            try:
                date = datetime.strptime(date.text, "%A, %d %B %Y:").date()
            except ValueError:
                _LOGGER.info(f"Skipped {date} as it does not match time format")
                continue
            img_tag = result.find("img")
            collection_type = img_tag["alt"]
            entries.append(
                Collection(
                    date=date,
                    t=collection_type,
                    icon=ICON_MAP.get(collection_type),
                )
            )
        return entries
