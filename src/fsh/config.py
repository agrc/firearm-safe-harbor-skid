"""
config.py: Configuration values. Secrets to be handled with Secrets Manager
"""

import logging

SKID_NAME = "firearm-safe-harbor-skid"

AGOL_ORG = "https://utah.maps.arcgis.com"
SENDGRID_SETTINGS = {
    "from_address": "noreply@utah.gov",
    "to_addresses": "ugrc-developers@utah.gov",
    "prefix": SKID_NAME,
}
LOG_LEVEL = logging.DEBUG
LOG_FILE_NAME = "log"
PARTICIPATION_COLUMN = "Firearm Safe Harbor (FSH) Participating"
COLUMNS = [
    "Firearm Safe Harbor (FSH) Participating",
    "NAME",
    "TELEPHONE",
    "FSH Phone",
    "Web Address",
    "FSH Email",
    "FSH Availability",
    "FSH Notes",
    "ADDRESS",
    "ADDRESS2",
    "X",
    "Y",
]
