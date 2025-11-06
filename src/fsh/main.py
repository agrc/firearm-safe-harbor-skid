#!/usr/bin/env python
# * coding: utf8 *
"""
Run the firearm safe harbor skid
"""

import json
import logging
import os
import socket
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pandas as pd
from arcgis.gis import GIS
from google.auth import default as google_auth_default
from palletjack import extract, load
from supervisor.message_handlers import SendGridHandler
from supervisor.models import MessageDetails, Supervisor

#: This makes it work when calling with just `python <file>`/installing via pip and in the gcf framework, where
#: the relative imports fail because of how it's calling the function.
try:
    from . import config, version
except ImportError:
    import config  # pyright: ignore[reportMissingImports]
    import version  # pyright: ignore[reportMissingImports]


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

        credentials, _ = google_auth_default()
        loader = extract.GSheetLoader(credentials)
        df = loader.load_specific_worksheet_into_dataframe(secrets.GOOGLE_SHEET_ID, worksheet=0)

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

        if config.COLUMNS:
            # keep only headers that exist in the sheet and in the include list, preserving order
            include_set = set(config.COLUMNS)
            keep = [h for h in df if h in include_set]
            df = df[keep]

        df[["X", "Y"]] = df[["X", "Y"]].apply(pd.to_numeric, errors="coerce")
        df = df.dropna(subset=["X", "Y"])

        valid_rows = len(df)
        module_logger.info("valid locations participating: %d", valid_rows)

        df = df.drop(columns=[config.PARTICIPATION_COLUMN], errors="ignore")
        df = df.rename(
            columns={
                "NAME": "name",
                "PHONE": "phone",
                "EMAIL": "email",
                "FSH AVAILABILITY": "hours",
                "FSH NOTES": "notes",
                "FULL_ADDRESS": "address",
                "ADDRESS2": "address2",
                "WEBSITE": "website",
                "GOOGLE": "url",
                "X": "longitude",
                "Y": "latitude",
            }
        )

        # Trim whitespace and convert empty strings to None for columns_to_clean
        columns_to_clean = ["phone", "email", "hours", "notes", "address2", "website"]
        for col in columns_to_clean:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
                df[col] = df[col].replace("", None)

        df["phone_url"] = df["phone"].apply(lambda x: f"tel:{x}" if pd.notna(x) else "")
        df = pd.DataFrame.spatial.from_xy(df, "longitude", "latitude", sr=4326)  # pyright: ignore[reportAttributeAccessIssue]

        gis = GIS(config.AGOL_ORG, secrets.AGOL_USERNAME, secrets.AGOL_PASSWORD)

        loader = load.ServiceUpdater(gis, secrets.FEATURE_LAYER_ITEMID, working_dir=tempdir_path)
        loader.truncate_and_load(df)

        end = datetime.now()
        service = os.environ.get("K_SERVICE") or os.environ.get("GAE_SERVICE") or socket.gethostname()
        project = (
            os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or os.environ.get("PROJECT_ID")
        )

        summary_message = MessageDetails()
        summary_message.subject = f"{config.SKID_NAME} Update Summary"
        summary_rows = [
            f"{config.SKID_NAME} update {start.strftime('%Y-%m-%d')}",
            "=" * 20,
            "",
            f"Service: {service}",
            f"Project: {project}",
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
