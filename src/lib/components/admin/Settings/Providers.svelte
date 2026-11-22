<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { createEventDispatcher } from 'svelte';
	import { toast } from 'svelte-sonner';

	import {
		applyProviders,
		createProvider,
		deleteProvider,
		getProviders,
		saveProviderModels,
		testProvider,
		testProviderDraft,
		updateProvider,
		type Provider,
		type ProviderDraft,
		type ProvidersState
	} from '$lib/apis/providers';

	import { PROVIDER_PRESETS, getPreset, providerFromPreset } from './Providers/presets';

	import ProviderCard from './Providers/ProviderCard.svelte';
	import AdminSettingSection from './AdminSettingSection.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte';
	import Link from '$lib/components/icons/Link.svelte';

	const i18n = getContext<typeof import('$lib/i18n').default>('i18n');
	const dispatch = createEventDispatcher();

	let providers: Provider[] = [];
	let drafts: (ProviderDraft & { id: string })[] = [];
	let state: ProvidersState = {};

	let loading = true;
	let applying = false;
	let savingId = '';
	let testingId = '';
	let testResults: Record<string, { count: number; latency_ms: number } | null> = {};
	let testErrors: Record<string, string> = {};
	let showDelete = false;
	let deleteId = '';

	const uid = () => `draft-${Math.random().toString(36).slice(2, 10)}`;

	// Recreate a card when its stored revision changes, so the form re-seeds.
	const providerKey = (provider: Provider) => `${provider.id}:${provider.updated_at ?? 'new'}`;

	const errorMessage = (error: unknown) =>
		typeof error === 'string' ? error : ((error as Error)?.message ?? String(error));

	const load = async () => {
		loading = true;
		try {
			const res = await getProviders(localStorage.token);
			providers = res?.providers ?? [];
			state = res?.state ?? {};
		} catch (error) {
			toast.error(errorMessage(error));
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		load();
	});

	const addPreset = (presetId: string) => {
		const preset = getPreset(presetId);
		if (!preset) return;
		drafts = [...drafts, { ...providerFromPreset(preset), id: uid() }];
	};

	const saveDraft = async (id: string, draft: ProviderDraft) => {
		savingId = id;
		try {
			if (id.startsWith('draft-')) {
				await createProvider(localStorage.token, draft);
				drafts = drafts.filter((entry) => entry.id !== id);
			} else {
				await updateProvider(localStorage.token, id, draft);
			}

			toast.success($i18n.t('Provider saved'));
			await load();
			dispatch('save');
		} catch (error) {
			toast.error(errorMessage(error));
		} finally {
			savingId = '';
		}
	};

	const testDraft = async (id: string, draft: ProviderDraft) => {
		testingId = id;
		testErrors = { ...testErrors, [id]: '' };

		try {
			const provider = providers.find((entry) => entry.id === id);

			// A saved provider without a freshly typed token is tested with its stored key.
			const result =
				provider && !draft.api_key
					? await testProvider(localStorage.token, id)
					: await testProviderDraft(localStorage.token, draft);

			testResults = { ...testResults, [id]: { count: result.count, latency_ms: result.latency_ms } };

			if (result.count === 0) {
				toast.warning($i18n.t('No models were returned by this provider'));
			} else {
				toast.success(`${$i18n.t('Connected')} · ${result.count}`);
			}
		} catch (error) {
			testResults = { ...testResults, [id]: null };
			testErrors = { ...testErrors, [id]: errorMessage(error) };
		} finally {
			testingId = '';
		}
	};

	const fetchModels = async (id: string) => {
		if (id.startsWith('draft-')) {
			toast.info($i18n.t('Save the provider before importing its model list'));
			return;
		}

		testingId = id;
		try {
			const res = await saveProviderModels(localStorage.token, id, true);
			toast.success(`${$i18n.t('Model List')}: ${res.count}`);
			await load();
		} catch (error) {
			toast.error(errorMessage(error));
		} finally {
			testingId = '';
		}
	};

	const removeProvider = async () => {
		const id = deleteId;
		showDelete = false;
		deleteId = '';
		if (!id) return;

		try {
			await deleteProvider(localStorage.token, id);
			toast.success($i18n.t('Provider deleted'));
			await load();
		} catch (error) {
			toast.error(errorMessage(error));
		}
	};

	const apply = async () => {
		applying = true;
		try {
			const res = await applyProviders(localStorage.token);
			state = res ?? {};
			toast.success(
				`${$i18n.t('Providers applied')} · ${res?.openai_connections ?? 0} + ${res?.ollama_connections ?? 0}`
			);
			await load();
			dispatch('save');
		} catch (error) {
			toast.error(errorMessage(error));
		} finally {
			applying = false;
		}
	};

	const appliedLabel = () => {
		if (!state?.applied_at) return $i18n.t('Not applied yet');
		const when = new Date(state.applied_at * 1000).toLocaleString();
		return `${$i18n.t('Last applied')}: ${when} · ${state.openai_connections ?? 0} + ${
			state.ollama_connections ?? 0
		}`;
	};
</script>

<div class="mt-1">
	<AdminSettingSection first={true}>
		<div class="flex items-start justify-between gap-3">
			<div>
				<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
					{$i18n.t('settings.admin.providers.title')}
				</div>
				<div class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t('settings.admin.providers.description')}
				</div>
			</div>

			<div class="flex shrink-0 items-center gap-1.5">
				<button
					class="flex items-center gap-1 rounded-lg p-1.5 text-gray-500 transition hover:bg-gray-50 dark:hover:bg-white/[0.06]"
					type="button"
					title={$i18n.t('Reload')}
					aria-label={$i18n.t('Reload')}
					on:click={load}
				>
					{#if loading}<Spinner />{:else}<ArrowPath className="size-3.5" />{/if}
				</button>

				<button
					class="flex items-center gap-1 rounded-lg bg-gray-900 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-gray-700 disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
					type="button"
					disabled={applying}
					on:click={apply}
				>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-3.5">
						<path
							fill-rule="evenodd"
							d="M13.797 3.944a2.725 2.725 0 012.263 3.923l.942 1.413a.75.75 0 01-.143.941l-6.63 6.05a2.75 2.75 0 01-3.79-.233L2.5 12.5a.75.75 0 01.06-1l1.9-1.72a2.75 2.75 0 013.9-.18l5.437-4.656zM3.451 11.943l2.76 2.99a1.25 1.25 0 001.725.106l1.66-1.516-2.372-2.57-1.66 1.515a1.25 1.25 0 00-.358.499z"
							clip-rule="evenodd"
						/>
					</svg>
					{$i18n.t('Apply')}
				</button>
			</div>
		</div>

		<div class="mt-2 flex flex-wrap items-center gap-1.5">
			{#each PROVIDER_PRESETS as preset (preset.id)}
				<button
					class="rounded-full border border-gray-100/70 px-2 py-0.5 text-[0.6875rem] text-gray-600 transition hover:border-gray-300 hover:text-gray-900 dark:border-white/[0.06] dark:text-gray-400 dark:hover:border-white/20 dark:hover:text-white"
					type="button"
					on:click={() => addPreset(preset.id)}
				>
					+ {preset.name}
				</button>
			{/each}

			<button
				class="flex items-center gap-1 rounded-full bg-gray-900/5 px-2 py-0.5 text-[0.6875rem] font-medium text-gray-700 transition hover:bg-gray-900/10 dark:bg-white/[0.06] dark:text-gray-200 dark:hover:bg-white/[0.1]"
				type="button"
				on:click={() => addPreset('custom')}
			>
				<Plus className="size-3" strokeWidth="2.5" />
				{$i18n.t('settings.admin.providers.add.label')}
			</button>
		</div>

		<div class="mt-2 flex items-center gap-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
			<Link className="size-3" strokeWidth="2" />
			{appliedLabel()}
		</div>
	</AdminSettingSection>

	<div class="mt-3 flex flex-col gap-2.5">
		{#each drafts as draft (draft.id)}
			<ProviderCard
				provider={draft}
				isNew={true}
				saving={savingId === draft.id}
				testing={testingId === draft.id}
				testResult={testResults[draft.id]}
				testError={testErrors[draft.id] ?? ''}
				on:save={(event) => saveDraft(draft.id, event.detail)}
				on:test={(event) => testDraft(draft.id, event.detail)}
				on:models={() => fetchModels(draft.id)}
				on:cancel={() => {
					drafts = drafts.filter((entry) => entry.id !== draft.id);
				}}
			/>
		{/each}

		{#each providers as provider (providerKey(provider))}
			<ProviderCard
				{provider}
				saving={savingId === provider.id}
				testing={testingId === provider.id}
				testResult={testResults[provider.id]}
				testError={testErrors[provider.id] ?? ''}
				on:save={(event) => saveDraft(provider.id, event.detail)}
				on:test={(event) => testDraft(provider.id, event.detail)}
				on:models={() => fetchModels(provider.id)}
				on:delete={() => {
					deleteId = provider.id;
					showDelete = true;
				}}
			/>
		{:else}
			{#if !loading && drafts.length === 0}
				<div
					class="rounded-2xl border border-dashed border-gray-200 px-3 py-6 text-center dark:border-white/[0.06]"
				>
					<div class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('No providers yet')}</div>
					<div class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t('settings.admin.providers.empty.description')}
					</div>
				</div>
			{/if}
		{/each}
	</div>
</div>

<ConfirmDialog
	bind:show={showDelete}
	title={$i18n.t('Delete')}
	message={$i18n.t('Are you sure you want to delete this provider?')}
	confirmLabel={$i18n.t('Delete')}
	on:confirm={removeProvider}
/>
