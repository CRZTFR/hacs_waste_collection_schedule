"""Register matching for councils on the waste-info.com.au platform.

Those councils expose the same v1 API: ``localities.json``, then
``streets.json?locality=`` and ``properties.json?street=``, each answering with
``{"name": ..., "id": ...}`` rows that a source has to match by name. The names
are the council's own register wording, and matching them literally is what
makes an ordinary address look unserviced:

- case and spacing vary ("berala" and "Merrylands  Road" are what people type,
  "Berala" and "Merrylands Road" is what the register holds);
- a property row may carry a building name between the number and the street
  ("4-12 five dock library Garfield Street Five Dock"), so the number, street
  and suburb are all correct and the row still does not compare equal.

Sources with their own richer matching (brisbane, impactapps, redland) are
untouched; this is for the ones that compared raw strings.
"""

from __future__ import annotations


def norm(value: object) -> str:
    """Register-comparable form: single-spaced and case-folded."""
    return " ".join(str(value or "").split()).casefold()


def same(a: object, b: object) -> bool:
    """True when two register names differ only by case or spacing."""
    return norm(a) == norm(b)


def property_matches(
    register_name: object, street_number: object, street_name: object, suburb: object
) -> bool:
    """True when a ``properties.json`` row is the address that was asked for.

    Accepts the register's canonical ``"<number> <street> <suburb>"`` and the
    same row with a building name inserted after the number. The number must
    still match in full, so "4-12" does not answer for "1m/4-12".
    """
    name = norm(register_name)
    if name == norm(f"{street_number} {street_name} {suburb}"):
        return True
    return name.startswith(norm(street_number) + " ") and name.endswith(
        norm(f"{street_name} {suburb}")
    )
