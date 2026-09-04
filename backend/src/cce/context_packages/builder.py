"""Build package versions from approved context assets."""

from cce.governance.policy import require_approved


def assert_assets_approved(assets) -> None:
    for asset in assets:
        require_approved(asset.status)
