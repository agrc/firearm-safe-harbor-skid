#!/usr/bin/env python
# * coding: utf8 *
"""
Run the firearm safe harbor script
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pandas as pd
from arcgis.gis import GIS
from google.auth import default as google_auth_default
from googleapiclient.discovery import build
from palletjack import load
from supervisor.message_handlers import SendGridHandler
from supervisor.models import MessageDetails, Supervisor

#: This makes it work when calling with just `python <file>`/installing via pip and in the gcf framework, where
#: the relative imports fail because of how it's calling the function.
try:
    from . import config, version
except ImportError:
    import config
    import version


def _get_secrets():
    """A helper method for loading secrets from either a GCF mount point or the local src/skidname/secrets/secrets.json file

    Raises:
        FileNotFoundError: If the secrets file can't be found.

    Returns:
        dict: The secrets .json loaded as a dictionary
    """

    secret_folder = Path("/secrets")

    #: Try to get the secrets from the Cloud Function mount point
    if secret_folder.exists():
        return json.loads(Path("/secrets/app/secrets.json").read_text(encoding="utf-8"))

    #: Otherwise, try to load a local copy for local development
    secret_folder = Path(__file__).parent / "secrets"
    if secret_folder.exists():
        return json.loads((secret_folder / "secrets.json").read_text(encoding="utf-8"))

    raise FileNotFoundError("Secrets folder not found; secrets not loaded.")


def _initialize(log_path, sendgrid_api_key):
    """A helper method to set up logging and supervisor

    Args:
        log_path (Path): File path for the logfile to be written
        sendgrid_api_key (str): The API key for sendgrid for this particular application

    Returns:
        Supervisor: The supervisor object used for sending messages
    """

    skid_logger = logging.getLogger(config.SKID_NAME)
    skid_logger.setLevel(config.LOG_LEVEL)
    palletjack_logger = logging.getLogger("palletjack")
    palletjack_logger.setLevel(config.LOG_LEVEL)

    cli_handler = logging.StreamHandler(sys.stdout)
    cli_handler.setLevel(config.LOG_LEVEL)
    formatter = logging.Formatter(
        fmt="%(levelname)-7s %(asctime)s %(name)15s:%(lineno)5s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    cli_handler.setFormatter(formatter)

    log_handler = logging.FileHandler(log_path, mode="w")
    log_handler.setLevel(config.LOG_LEVEL)
    log_handler.setFormatter(formatter)

    skid_logger.addHandler(cli_handler)
    skid_logger.addHandler(log_handler)
    palletjack_logger.addHandler(cli_handler)
    palletjack_logger.addHandler(log_handler)

    #: Log any warnings at logging.WARNING
    #: Put after everything else to prevent creating a duplicate, default formatter
    #: (all log messages were duplicated if put at beginning)
    logging.captureWarnings(True)

    skid_supervisor = Supervisor(handle_errors=False)
    sendgrid_settings = config.SENDGRID_SETTINGS
    sendgrid_settings["api_key"] = sendgrid_api_key
    skid_supervisor.add_message_handler(
        SendGridHandler(
            sendgrid_settings=sendgrid_settings, client_name=config.SKID_NAME, client_version=version.__version__
        )
    )

    return skid_supervisor


def _load_sheet_to_dataframe(spreadsheet_id: str, worksheet_index: int = 0, include_columns=None, exclude_columns=None):
    """Load a Google Sheets worksheet into a pandas.DataFrame using Application Default Credentials.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet id.
        worksheet_index: Zero-based worksheet index to load.

        include_columns: optional list of header names to keep (applies after reading header)
        exclude_columns: optional list of header names to drop

    Returns:
        pandas.DataFrame

    Raises:
        RuntimeError: if required libraries are not installed.
    """

    if google_auth_default is None or build is None or pd is None:
        raise RuntimeError(
            "google-auth, google-api-python-client and pandas are required to load Google Sheets; install them in your venv"
        )

    credentials, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    service = build("sheets", "v4", credentials=credentials)

    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = meta.get("sheets", [])

    if not sheets:
        return pd.DataFrame()

    if worksheet_index < 0 or worksheet_index >= len(sheets):
        raise IndexError(f"Worksheet index {worksheet_index} out of range (found {len(sheets)} sheets)")

    title = sheets[worksheet_index]["properties"]["title"]

    sheet = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=title).execute()
    values = sheet.get("values", [])
    if not values:
        return pd.DataFrame()

    # Normalize row lengths and construct DataFrame using first row as header
    max_cols = max(len(r) for r in values)
    rows = [r + [""] * (max_cols - len(r)) for r in values]
    header = rows[0]
    data_rows = rows[1:]

    # Normalize headers and build DataFrame
    header = [h.strip() if isinstance(h, str) else h for h in header]
    df = pd.DataFrame(data_rows, columns=header)

    # Trim whitespace in all string/object columns
    str_cols = df.select_dtypes(include="object").columns
    if len(str_cols):
        df[str_cols] = df[str_cols].apply(lambda s: s.str.strip())

    # Normalize common empty tokens to real missing values
    na_tokens = [""]
    df.replace(na_tokens, pd.NA, inplace=True)
    # Catch whitespace-only strings if any slipped through
    df.replace(r"^\s*$", pd.NA, regex=True, inplace=True)

    # If caller requested only a subset of columns, apply include/exclude by header name
    if include_columns:
        # keep only headers that exist in the sheet and in the include list, preserving order
        include_set = set(include_columns)
        keep = [h for h in header if h in include_set]
        df = df[keep]
    elif exclude_columns:
        drop = [h for h in header if h in (exclude_columns or []) and h in header]
        if drop:
            df = df.drop(columns=drop)

    return df


def process():
    """The main function that does all the work."""

    #: Set up secrets, tempdir, supervisor, and logging
    start = datetime.now()

    secrets = SimpleNamespace(**_get_secrets())

    with TemporaryDirectory() as tempdir:
        tempdir_path = Path(tempdir)
        log_name = f"{config.LOG_FILE_NAME}_{start.strftime('%Y%m%d-%H%M%S')}.txt"
        log_path = tempdir_path / log_name

        skid_supervisor = _initialize(log_path, secrets.SENDGRID_API_KEY)
        module_logger = logging.getLogger(config.SKID_NAME)
        module_logger.info("starting %s version %s", config.SKID_NAME, version.__version__)

        df = _load_sheet_to_dataframe(
            secrets.GOOGLE_SHEET_ID,
            worksheet_index=0,
            include_columns=config.COLUMNS,
        )

        total_rows = len(df)
        module_logger.debug("total rows in sheet: %d", total_rows)

        if config.PARTICIPATION_COLUMN not in df.columns:
            module_logger.warning(
                "Participation column not found in DataFrame; no rows filtered. Available columns: %s",
                list(df.columns),
            )

            raise ValueError(
                f"Column '{config.PARTICIPATION_COLUMN}' not found in DataFrame. Available columns: {list(df.columns)}"
            )
        else:
            df = df[df[config.PARTICIPATION_COLUMN].fillna("").astype(str).str.strip().str.upper() == "Y"]

            participating_rows = len(df)
            module_logger.info("locations participating: %d", participating_rows)

        df[["X", "Y"]] = df[["X", "Y"]].apply(pd.to_numeric, errors="coerce")
        df = df.dropna(subset=["X", "Y"])

        valid_rows = len(df)
        module_logger.info("valid locations participating: %d", valid_rows)

        df = df.drop(columns=[config.PARTICIPATION_COLUMN], errors="ignore")
        df = df.rename(
            columns={
                "NAME": "name",
                "FSH Phone": "phone",
                "FSH Email": "email",
                "FSH Availability": "hours",
                "FSH Notes": "notes",
                "TELEPHONE": "phone_other",
                "ADDRESS": "address",
                "ADDRESS2": "address2",
                "Web Address": "url",
                "X": "longitude",
                "Y": "latitude",
            }
        )

        df = pd.DataFrame.spatial.from_xy(df, "longitude", "latitude", sr=4326)

        gis = GIS(config.AGOL_ORG, secrets.AGOL_USERNAME, secrets.AGOL_PASSWORD)

        loader = load.ServiceUpdater(gis, secrets.FEATURE_LAYER_ITEMID, working_dir=tempdir_path)
        loader.truncate_and_load(df)

        end = datetime.now()

        summary_message = MessageDetails()
        summary_message.subject = f"{config.SKID_NAME} Update Summary"
        summary_rows = [
            f"{config.SKID_NAME} update {start.strftime('%Y-%m-%d')}",
            "=" * 20,
            "",
            f"Start time: {start.strftime('%H:%M:%S')}",
            f"End time: {end.strftime('%H:%M:%S')}",
            f"Duration: {str(end - start)}",
            f"Total rows in sheet: {total_rows}",
            f"Rows participating: {participating_rows}",
            f"Rows with geometry: {valid_rows}",
        ]

        summary_message.message = "\n".join(summary_rows)
        summary_message.attachments = tempdir_path / log_name

        # Only send notifications when running in a cloud environment (e.g. GCF mounts /secrets)
        if Path("/secrets").exists():
            skid_supervisor.notify(summary_message)
        else:
            module_logger.info("Not sending notification: running in local/dev environment")


if __name__ == "__main__":
    process()
