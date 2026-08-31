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
            print("⚠️ 没有提供上游provider UUIDs，跳过上游合并")
            return None

        print(f"\n🔗 开始上游供应链合并...")
        print(f"  - 产品系统UUID: {system_uuid}")
        print(f"  - 上游Providers数量: {len(upstream_provider_uuids)}")

        if linking_config is None:
            linking_config = o.LinkingConfig(
                prefer_unit_processes=False,
                provider_linking=o.ProviderLinking.PREFER_DEFAULTS,
            )

        cutoff_value = CUTOFF_THRESHOLD
        if cutoff_value is not None:
            print(
                f"  ✓ 应用截断阈值: {cutoff_value * 100}%（贡献度低于此值的上游链将被截断）"
            )

        result = merge_upstream_systems_into_original(
            client=self.client,
            system_uuid=system_uuid,
            upstream_provider_uuids=upstream_provider_uuids,
            linking_config=linking_config,
            cutoff=cutoff_value,
        )

        if result:
            print(f"\n✅ 上游供应链合并完成: {result.name}")
        else:
            print(f"\n✗ 上游供应链合并失败")

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

    print("UpstreamMerger模块 - 用于合并上游供应链")
    print("使用示例:")
    print("  merger = UpstreamMerger(client)")
    print("  result = merger.merge_upstream_chains(system_uuid, provider_uuids)")
