from typing import List, Optional

import olca_ipc as ipc
import olca_schema as o
from .merge_upstream_systems_unchanged import (
    create_upstream_system,
    merge_upstream_systems_into_original,
)
from .config import CUTOFF_THRESHOLD


class UpstreamMerger:

    def __init__(self, client: ipc.Client):

        self.client = client

    def merge_upstream_chains(
        self,
        system_uuid: str,
        upstream_provider_uuids: List[str],
        linking_config: o.LinkingConfig = None,
    ) -> Optional[o.Ref]:

        if not upstream_provider_uuids:
            print("⚠️ No upstream provider UUIDs provided; skipping upstream merge")
            return None

        print(f"\n🔗 Starting upstream supply-chain merge...")
        print(f"  - Product system UUID: {system_uuid}")
        print(f"  - Upstream provider count: {len(upstream_provider_uuids)}")

        if linking_config is None:
            linking_config = o.LinkingConfig(
                prefer_unit_processes=False,
                provider_linking=o.ProviderLinking.PREFER_DEFAULTS,
            )

        cutoff_value = CUTOFF_THRESHOLD
        if cutoff_value is not None:
            print(
                f"  ✓ Applying cutoff threshold: {cutoff_value * 100}% (upstream chains below this contribution will be truncated)"
            )

        result = merge_upstream_systems_into_original(
            client=self.client,
            system_uuid=system_uuid,
            upstream_provider_uuids=upstream_provider_uuids,
            linking_config=linking_config,
            cutoff=cutoff_value,
        )

        if result:
            print(f"\n✅ Upstream supply-chain merge completed: {result.name}")
        else:
            print(f"\n✗ Upstream supply-chain merge failed")

        return result

    def merge_selective_upstream(
        self,
        system_uuid: str,
        provider_selection: dict,
        linking_config: o.LinkingConfig = None,
    ) -> Optional[o.Ref]:

        provider_uuids = []
        for key, data in provider_selection.items():
            provider_ref = data.get("ref")
            if provider_ref and hasattr(provider_ref, "id"):
                provider_uuids.append(provider_ref.id)

        provider_uuids = list(set(provider_uuids))

        return self.merge_upstream_chains(system_uuid, provider_uuids, linking_config)


if __name__ == "__main__":

    print("UpstreamMerger module - merge upstream supply chains")
    print("Usage example:")
    print("  merger = UpstreamMerger(client)")
    print("  result = merger.merge_upstream_chains(system_uuid, provider_uuids)")
