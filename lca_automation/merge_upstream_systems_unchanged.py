import olca_ipc as ipc
import olca_schema as o
from typing import List


def create_upstream_system(
    client: ipc.Client, provider_ref: o.Ref, linking_config: o.LinkingConfig
) -> o.ProductSystem:

    try:
        temp_system_ref = client.create_product_system(provider_ref, linking_config)
        return client.get(o.ProductSystem, temp_system_ref.id)
    except Exception as e:
        print(f"✗ 创建上游系统失败: {e}")
        return None


def merge_upstream_systems_into_original(
    client: ipc.Client,
    system_uuid: str,
    upstream_provider_uuids: List[str],
    linking_config: o.LinkingConfig = None,
    cutoff: float = None,
):

    print("步骤 6.1：获取原系统")
    try:
        original_system = client.get(o.ProductSystem, system_uuid)
        if not original_system:
            raise Exception(f"找不到系统 {system_uuid}")

        original_processes = (
            list(original_system.processes) if original_system.processes else []
        )
        original_links = (
            list(original_system.process_links) if original_system.process_links else []
        )

        print(
            f"✓ {original_system.name} - 过程:{len(original_processes)}, 连接:{len(original_links)}"
        )
    except Exception as e:
        print(f"✗ 获取原系统失败: {e}")
        return None

    if linking_config is None:
        linking_config = o.LinkingConfig(
            prefer_unit_processes=False,
            provider_linking=o.ProviderLinking.PREFER_DEFAULTS,
        )

    if cutoff is not None:
        linking_config.cutoff = cutoff
        print(f"  ✓ 截断阈值: {cutoff * 100}%（贡献度低于此值的上游链将被截断）")

    print(f"\n步骤 6.2：创建 {len(upstream_provider_uuids)} 个上游系统")

    all_upstream_systems = []

    for i, provider_uuid in enumerate(upstream_provider_uuids, 1):
        try:
            provider_ref = o.Ref(id=provider_uuid, ref_type=o.RefType.Process)
            provider_process = client.get(o.Process, provider_uuid)
            provider_name = (
                provider_process.name if provider_process else provider_uuid[:8]
            )

            upstream_system = create_upstream_system(
                client, provider_ref, linking_config
            )

            if upstream_system:
                proc_count = (
                    len(upstream_system.processes) if upstream_system.processes else 0
                )
                link_count = (
                    len(upstream_system.process_links)
                    if upstream_system.process_links
                    else 0
                )
                print(
                    f"  [{i}/{len(upstream_provider_uuids)}] ✓ {provider_name}: {proc_count}过程, {link_count}连接"
                )

                all_upstream_systems.append(
                    {
                        "system": upstream_system,
                        "provider_name": provider_name,
                        "provider_uuid": provider_uuid,
                    }
                )
            else:
                print(
                    f"  [{i}/{len(upstream_provider_uuids)}] ✗ {provider_name[:20]}: 创建失败"
                )

        except Exception as e:
            print(f"  [{i}/{len(upstream_provider_uuids)}] ✗ 处理失败: {e}")
            continue

    if not all_upstream_systems:
        print("✗ 没有成功创建任何上游系统")
        return None

    print("\n步骤 6.3：合并上游系统")

    merged_processes_dict = {p.id: p for p in original_processes}
    merged_links_dict = {}
    duplicate_link_count = 0
    skipped_self_loop_links = 0
    for link in original_links:
        if _is_self_loop_link(link):
            skipped_self_loop_links += 1
            continue
        key = _link_key(link)
        if key in merged_links_dict:
            duplicate_link_count += 1
            continue
        merged_links_dict[key] = link

    for upstream_info in all_upstream_systems:
        upstream_system = upstream_info["system"]
        upstream_processes = (
            list(upstream_system.processes) if upstream_system.processes else []
        )
        upstream_links = (
            list(upstream_system.process_links) if upstream_system.process_links else []
        )

        for proc_ref in upstream_processes:
            if proc_ref.id not in merged_processes_dict:
                merged_processes_dict[proc_ref.id] = proc_ref

        for link in upstream_links:
            if _is_self_loop_link(link):
                skipped_self_loop_links += 1
                continue
            link_key = _link_key(link)
            if link_key not in merged_links_dict:
                merged_links_dict[link_key] = link
            else:
                duplicate_link_count += 1

    merged_processes = list(merged_processes_dict.values())
    merged_links = list(merged_links_dict.values())

    print(
        f"✓ 合并完成: {len(original_processes)}→{len(merged_processes)}过程, {len(original_links)}→{len(merged_links)}连接"
    )
    if duplicate_link_count > 0:
        print(
            f"ℹ️ ProcessLink 去重数量: {duplicate_link_count}（按 process/provider/exchange/flow 复合键）"
        )
    if skipped_self_loop_links > 0:
        print(
            f"ℹ️ ProcessLink 自环过滤数量: {skipped_self_loop_links}（process.id == provider.id）"
        )

    print("\n步骤 6.4：保存系统")
    try:
        original_system.processes = merged_processes
        original_system.process_links = merged_links

        import datetime

        update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        upstream_names = ", ".join(
            [info["provider_name"] for info in all_upstream_systems]
        )
        update_msg = f"\n[增量更新于 {update_time}，添加上游供应链: {upstream_names}]"
        original_system.description = (original_system.description or "") + update_msg

        client.put(original_system)
        print(f"✓ 已保存: {original_system.name}")
    except Exception as e:
        print(f"✗ 保存失败: {e}")
        return None

    print("\n步骤 6.5：清理临时系统")
    for upstream_info in all_upstream_systems:
        try:
            temp_ref = o.Ref(
                id=upstream_info["system"].id, ref_type=o.RefType.ProductSystem
            )
            client.delete(temp_ref)
            print(f"  ✓ 已删除: {upstream_info['provider_name']}")
        except Exception:
            print(f"  ⚠️ 删除失败: {upstream_info['provider_name']}")

    return o.Ref(
        id=original_system.id,
        name=original_system.name,
        ref_type=o.RefType.ProductSystem,
    )


def _link_key(link):

    process_id = getattr(getattr(link, "process", None), "id", "None")
    provider_id = getattr(getattr(link, "provider", None), "id", "None")
    exchange_id = getattr(getattr(link, "exchange", None), "internal_id", None)
    flow_id = getattr(getattr(link, "flow", None), "id", "None")
    return (str(process_id), str(provider_id), str(exchange_id), str(flow_id))


def _is_self_loop_link(link):

    process_id = getattr(getattr(link, "process", None), "id", None)
    provider_id = getattr(getattr(link, "provider", None), "id", None)
    return bool(process_id and provider_id and process_id == provider_id)


def main():

    client = ipc.Client()

    system_uuid = "436f2ef6-1e0a-43e8-a833-07bdd894dd20"

    upstream_provider_uuids = [
        "b5a7d835-4e64-34f9-88b0-4ef16d88693a",
        "036e309b-99a9-3f0e-91d5-cc9eebcc0cec",
    ]

    CUTOFF = 0.05

    print("=" * 70)
    print("合并上游供应链到产品系统")
    print("=" * 70)
    print(f"\n配置信息:")
    print(f"  - 目标系统: {system_uuid}")
    print(f"  - 上游供应商数量: {len(upstream_provider_uuids)}")
    if CUTOFF is not None:
        print(f"  - 截断阈值: {CUTOFF * 100}% (减少系统复杂度)")
        print(f"    说明: 贡献度低于{CUTOFF * 100}%的上游链将被截断")
    else:
        print(f"  - 截断阈值: 未设置 (展开所有上游链)")
    print()

    linking_config = o.LinkingConfig(
        prefer_unit_processes=False,
        provider_linking=o.ProviderLinking.PREFER_DEFAULTS,
    )

    result = merge_upstream_systems_into_original(
        client=client,
        system_uuid=system_uuid,
        upstream_provider_uuids=upstream_provider_uuids,
        linking_config=linking_config,
        cutoff=CUTOFF,
    )

    if result:
        print(f"\n{'='*70}")
        print(f"✓ 合并完成: {result.name}")
        print("=" * 70)
    else:
        print("\n✗ 合并失败")


if __name__ == "__main__":
    main()
