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
        print(f"✗ Failed to create upstream system: {e}")
        return None


def merge_upstream_systems_into_original(
    client: ipc.Client,
    system_uuid: str,
    upstream_provider_uuids: List[str],
    linking_config: o.LinkingConfig = None,
    cutoff: float = None,
):

    print("Step 6.1: Get original system")
    try:
        original_system = client.get(o.ProductSystem, system_uuid)
        if not original_system:
            raise Exception(f"System not found: {system_uuid}")

        original_processes = (
            list(original_system.processes) if original_system.processes else []
        )
        original_links = (
            list(original_system.process_links) if original_system.process_links else []
        )

        print(
            f"✓ {original_system.name} - processes:{len(original_processes)}, links:{len(original_links)}"
        )
    except Exception as e:
        print(f"✗ Failed to get original system: {e}")
        return None

    if linking_config is None:
        linking_config = o.LinkingConfig(
            prefer_unit_processes=False,
            provider_linking=o.ProviderLinking.PREFER_DEFAULTS,
        )

    if cutoff is not None:
        linking_config.cutoff = cutoff
        print(f"  ✓ Cutoff threshold: {cutoff * 100}% (upstream chains below this contribution will be truncated)")

    print(f"\nStep 6.2: Create {len(upstream_provider_uuids)} upstream systems")

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
                    f"  [{i}/{len(upstream_provider_uuids)}] ✓ {provider_name}: {proc_count} processes, {link_count} links"
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
                    f"  [{i}/{len(upstream_provider_uuids)}] ✗ {provider_name[:20]}: creation failed"
                )

        except Exception as e:
            print(f"  [{i}/{len(upstream_provider_uuids)}] ✗ Processing failed: {e}")
            continue

    if not all_upstream_systems:
        print("✗ No upstream systems were created successfully")
        return None

    print("\nStep 6.3: Merge upstream systems")

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
        f"✓ Merge completed: {len(original_processes)}→{len(merged_processes)} processes, {len(original_links)}→{len(merged_links)} links"
    )
    if duplicate_link_count > 0:
        print(
            f"ℹ️ ProcessLink duplicates removed: {duplicate_link_count} (by process/provider/exchange/flow composite key)"
        )
    if skipped_self_loop_links > 0:
        print(
            f"ℹ️ ProcessLink self-loops filtered: {skipped_self_loop_links} (process.id == provider.id)"
        )

    print("\nStep 6.4: Save system")
    try:
        original_system.processes = merged_processes
        original_system.process_links = merged_links

        import datetime

        update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        upstream_names = ", ".join(
            [info["provider_name"] for info in all_upstream_systems]
        )
        update_msg = f"\n[Incremental update at {update_time}, added upstream supply chains: {upstream_names}]"
        original_system.description = (original_system.description or "") + update_msg

        client.put(original_system)
        print(f"✓ Saved: {original_system.name}")
    except Exception as e:
        print(f"✗ Save failed: {e}")
        return None

    print("\nStep 6.5: Clean up temporary systems")
    for upstream_info in all_upstream_systems:
        try:
            temp_ref = o.Ref(
                id=upstream_info["system"].id, ref_type=o.RefType.ProductSystem
            )
            client.delete(temp_ref)
            print(f"  ✓ Deleted: {upstream_info['provider_name']}")
        except Exception:
            print(f"  ⚠️ Delete failed: {upstream_info['provider_name']}")

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
    print("Merge upstream supply chains into product system")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  - Target system: {system_uuid}")
    print(f"  - Upstream provider count: {len(upstream_provider_uuids)}")
    if CUTOFF is not None:
        print(f"  - Cutoff threshold: {CUTOFF * 100}% (reduce system complexity)")
        print(f"    Note: upstream chains with contribution below {CUTOFF * 100}% will be truncated")
    else:
        print(f"  - Cutoff threshold: not set (expand all upstream chains)")
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
        print(f"✓ Merge completed: {result.name}")
        print("=" * 70)
    else:
        print("\n✗ Merge failed")


if __name__ == "__main__":
    main()
