"""
Roll number encoding — SPEC Module 1 [LOCKED] default scheme.

Default: [DaySet 3-digit bitmask][TimeCode 2-digit hour][Serial 3-digit]
Example: Sat+Mon+Wed (1+4+16=21) @ 14:00 serial 33 → 02114033

Centres may switch to plain serial or custom encoding via Settings;
the default scheme remains available for origin-client compatibility.
"""

from __future__ import annotations

from typing import List, Optional, Tuple
from models.admission import days_to_bitmask, bitmask_to_days, DAY_BITS


class RollEncoder:
    """Encode / decode / next-serial for student roll numbers."""

    SCHEME_BITMASK = 'bitmask'   # LOCKED default
    SCHEME_PLAIN = 'plain'       # plain serial only
    SCHEME_CUSTOM = 'custom'

    def __init__(self, scheme: str = SCHEME_BITMASK, custom_pattern: Optional[str] = None):
        if scheme not in (self.SCHEME_BITMASK, self.SCHEME_PLAIN, self.SCHEME_CUSTOM):
            raise ValueError(f"Unknown roll scheme: {scheme}")
        self.scheme = scheme
        self.custom_pattern = custom_pattern

    def encode(self, days: List[str], hour: int, serial: int) -> str:
        """Build roll string for the active scheme."""
        if not (0 <= hour <= 23):
            raise ValueError(f"hour must be 0–23, got {hour}")
        if not (1 <= serial <= 999):
            raise ValueError(f"serial must be 1–999, got {serial}")

        if self.scheme == self.SCHEME_PLAIN:
            return f"{serial:03d}"

        if self.scheme == self.SCHEME_CUSTOM:
            # Minimal custom: {serial} only unless pattern provided
            if self.custom_pattern:
                return self.custom_pattern.format(
                    dayset=f"{days_to_bitmask(days):03d}",
                    hour=f"{hour:02d}",
                    serial=f"{serial:03d}",
                )
            return f"{serial:03d}"

        # Default LOCKED bitmask scheme
        dayset = days_to_bitmask(days)
        return f"{dayset:03d}{hour:02d}{serial:03d}"

    def encode_from_bitmask(self, day_bitmask: int, hour: int, serial: int) -> str:
        days = bitmask_to_days(day_bitmask)
        return self.encode(days, hour, serial)

    def decode(self, roll: str) -> Optional[Tuple[int, int, int]]:
        """
        Decode bitmask-scheme roll → (day_bitmask, hour, serial).
        Returns None if roll does not match the 8-digit bitmask format.
        """
        if self.scheme != self.SCHEME_BITMASK:
            return None
        if not roll or len(roll) != 8 or not roll.isdigit():
            return None
        dayset = int(roll[0:3])
        hour = int(roll[3:5])
        serial = int(roll[5:8])
        if dayset < 1 or dayset > 127:
            return None
        if hour > 23:
            return None
        if serial < 1:
            return None
        return dayset, hour, serial

    def next_serial(self, existing_rolls: List[str], days: List[str], hour: int) -> int:
        """
        Next available serial for this batch slot (days+hour).
        Scans existing rolls for the same dayset+hour prefix.
        """
        if self.scheme == self.SCHEME_PLAIN:
            used = set()
            for r in existing_rolls:
                if r.isdigit():
                    used.add(int(r))
            serial = 1
            while serial in used and serial <= 999:
                serial += 1
            if serial > 999:
                raise ValueError("Serial space exhausted (1–999)")
            return serial

        dayset = days_to_bitmask(days)
        prefix = f"{dayset:03d}{hour:02d}"
        used = set()
        for r in existing_rolls:
            if len(r) == 8 and r.startswith(prefix) and r.isdigit():
                used.add(int(r[5:8]))
        serial = 1
        while serial in used and serial <= 999:
            serial += 1
        if serial > 999:
            raise ValueError(f"Serial space exhausted for prefix {prefix}")
        return serial

    @staticmethod
    def validate_example() -> str:
        """SPEC example: Sat+Mon+Wed 14:00 serial 33 → 02114033"""
        enc = RollEncoder()
        result = enc.encode(['sat', 'mon', 'wed'], 14, 33)
        assert result == '02114033', f"LOCKED example failed: got {result}"
        decoded = enc.decode(result)
        assert decoded == (21, 14, 33)
        return result
