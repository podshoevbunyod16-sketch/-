<script lang="ts">
	import { getContext } from 'svelte';
	import { createEventDispatcher } from 'svelte';

	import type { Provider, ProviderAuthStyle, ProviderDraft, ProviderKind } from '$lib/apis/providers';
	import { AUTH_STYLE_LABELS, PROVIDER_KIND_LABELS } from './presets';

	const i18n = getContext<typeof import('$lib/i18n').default>('i18n');
	const dispatch = createEventDispatcher();

	export let provider: Provider;
	export let isNew = false;
	export let saving = false;
	export let testing = false;
	export let testResult: { count: number; latency_ms: number } | null | undefined = null;
	export let testError = '';

	// The parent keys this component by the provider's revision, so seeding the
	// form from the props once is enough - a reloaded provider remounts the card.
	let name = provider?.name ?? '';
	let kind: ProviderKind = (provider?.kind as ProviderKind) ?? 'openai';
	let baseUrl = provider?.base_url ?? '';
	let apiKey = provider?.api_key ?? '';
	let authStyle: ProviderAuthStyle = (provider?.auth_style as ProviderAuthStyle) ?? 'bearer';
	let authHeader = provider?.auth_header || 'Authorization';
	let prefixId = provider?.prefix_id ?? '';
	let notes = provider?.notes ?? '';
	let enabled = provider?.enabled ?? true;
	let modelText = (provider?.model_ids ?? []).join('\n');
	let headerRows: { key: string; value: string }[] = Object.entries(provider?.headers ?? {}).map(
		([key, value]) => ({ key, value })
	);

	let showAdvanced = false;
	let clearKey = false;

	$: modelIds = modelText
		.split(/[\n,]/)
		.map((entry) => entry.trim())
		.filter((entry) => entry.length > 0);

	$: dirty =
		clearKey ||
		name !== (provider?.name ?? '') ||
		kind !== provider?.kind ||
		baseUrl !== (provider?.base_url ?? '') ||
		apiKey !== '' ||
		authStyle !== (provider?.auth_style ?? 'bearer') ||
		authHeader !== (provider?.auth_header || 'Authorization') ||
		prefixId !== (provider?.prefix_id ?? '') ||
		notes !== (provider?.notes ?? '') ||
		enabled !== (provider?.enabled ?? true) ||
		modelIds.join('\n') !== (provider?.model_ids ?? []).join('\n') ||
		JSON.stringify(headerRows.filter((row) => row.key.trim())) !==
			JSON.stringify(Object.entries(provider?.headers ?? {}).map(([key, value]) => ({ key, value })));

	$: draft = buildDraft();

	function buildDraft(): ProviderDraft {
		const headers: Record<string, string> = {};
		for (const row of headerRows) {
			const key = row.key.trim();
			if (key) headers[key] = row.value;
		}

		return {
			name: name.trim() || `${PROVIDER_KIND_LABELS[kind] ?? kind}`,
			kind,
			base_url: baseUrl.trim().replace(/\/+$/, ''),
			// An untouched empty field must not wipe a stored token.
			api_key: clearKey ? '' : isNew || apiKey !== '' ? apiKey : undefined,
			auth_style: authStyle,
			auth_header: authHeader.trim() || 'Authorization',
			model_ids: modelIds,
			headers,
			prefix_id: prefixId.trim(),
			enabled,
			notes: notes.trim()
		};
	}

	const inputClass =
		'w-full text-sm text-gray-700 dark:text-gray-300 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-700';
	const fieldClass =
		'flex w-full items-center rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 py-1.5 transition-colors focus-within:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:focus-within:border-blue-500';
	const selectClass =
		'w-full bg-transparent text-sm text-gray-700 dark:text-gray-300 outline-hidden appearance-none';

	const labelText = (key: string) => $i18n.t(key);

	const save = () => dispatch('save', draft);
	const test = () => dispatch('test', draft);
	const fetchModels = () => dispatch('models');
	const remove = () => dispatch('delete');
</script>

<div
	class="rounded-2xl border border-gray-100/60 bg-white p-3 dark:border-white/[0.04] dark:bg-white/[0.02] {provider?.enabled === false && !isNew
		? 'opacity-60'
		: ''}"
>
	<div class="flex flex-wrap items-start gap-2">
		<div class="{fieldClass} min-w-[9rem] flex-1">
			<input
				class={inputClass}
				bind:value={name}
				placeholder={$i18n.t('Name')}
				aria-label={$i18n.t('settings.admin.providers.name.label')}
			/>
		</div>

		<div class="{fieldClass} w-full sm:w-[11rem]">
			<select class={selectClass} bind:value={kind} aria-label={$i18n.t('settings.admin.providers.kind.label')}>
				{#each Object.entries(PROVIDER_KIND_LABELS) as [value, label]}
					<option {value}>{label}</option>
				{/each}
			</select>
		</div>

		<button
			class="self-center p-1 text-gray-400 transition hover:text-gray-700 dark:hover:text-gray-300"
			type="button"
			aria-label={enabled ? $i18n.t('Enabled') : $i18n.t('Disabled')}
			aria-pressed={enabled}
			on:click={() => {
				enabled = !enabled;
			}}
			title={enabled ? $i18n.t('Enabled') : $i18n.t('Disabled')}
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 24 24"
				fill="currentColor"
				class="size-4 {enabled ? 'text-green-500' : 'text-gray-300 dark:text-gray-700'}"
			>
				<path
					fill-rule="evenodd"
					d="M21.731 2.269a.75.75 0 010 1.06l-12.5 12.5a.75.75 0 01-1.06 0l-5.5-5.5a.75.75 0 011.06-1.06L8.5 14.19 20.671 2.269a.75.75 0 011.06 0z"
					clip-rule="evenodd"
				/>
			</svg>
		</button>
	</div>

	<div class="mt-2 grid gap-2 sm:grid-cols-2">
		<div>
			<label class="text-[0.6875rem] text-gray-500 dark:text-gray-400" for="providers-{provider?.id}-url">
				{$i18n.t('settings.admin.providers.baseUrl.label')}
			</label>
			<div class="{fieldClass} mt-1">
				<input
					id="providers-{provider?.id}-url"
					class={inputClass}
					bind:value={baseUrl}
					autocomplete="off"
					spellcheck="false"
					placeholder="https://api.example.com/v1"
				/>
			</div>
		</div>

		<div>
			<label class="text-[0.6875rem] text-gray-500 dark:text-gray-400" for="providers-{provider?.id}-key">
				{$i18n.t('settings.admin.providers.apiKey.label')}
			</label>
			<div class="{fieldClass} mt-1">
				<input
					id="providers-{provider?.id}-key"
					class={inputClass}
					type="password"
					bind:value={apiKey}
					autocomplete="new-password"
					spellcheck="false"
					placeholder={provider?.api_key_masked || $i18n.t('API Key')}
				/>
				{#if provider?.has_key && apiKey === ''}
					<button
						class="shrink-0 text-[0.6875rem] text-gray-400 transition hover:text-red-500"
						type="button"
						on:click={() => {
							clearKey = !clearKey;
						}}
					>
						{clearKey ? $i18n.t('Keep the stored key') : $i18n.t('Clear the stored key')}
					</button>
				{/if}
			</div>
		</div>
	</div>

	<div class="mt-2">
		<button
			class="flex items-center gap-1 text-[0.6875rem] text-gray-500 transition hover:text-gray-800 dark:hover:text-gray-300"
			type="button"
			on:click={() => {
				showAdvanced = !showAdvanced;
			}}
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 20 20"
				fill="currentColor"
				class="size-3 transition-transform {showAdvanced ? 'rotate-90' : ''}"
			>
				<path
					fill-rule="evenodd"
					d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
					clip-rule="evenodd"
				/>
			</svg>
			{$i18n.t('Advanced')}
			{#if modelIds.length > 0}
				· {modelIds.length} {$i18n.t('Models').toLowerCase()}
			{/if}
		</button>

		{#if showAdvanced}
			<div class="mt-2 grid gap-2 sm:grid-cols-2">
				<div>
					<label
						class="text-[0.6875rem] text-gray-500 dark:text-gray-400"
						for="providers-{provider?.id}-auth">{labelText('settings.admin.providers.auth.label')}</label
					>
					<div class="{fieldClass} mt-1">
						<select
							id="providers-{provider?.id}-auth"
							class={selectClass}
							bind:value={authStyle}
						>
							{#each Object.entries(AUTH_STYLE_LABELS) as [value, label]}
								<option {value}>{label}</option>
							{/each}
						</select>
					</div>
				</div>

				{#if authStyle === 'header'}
					<div>
						<label
							class="text-[0.6875rem] text-gray-500 dark:text-gray-400"
							for="providers-{provider?.id}-auth-header"
							>{labelText('settings.admin.providers.authHeader.label')}</label
						>
						<div class="{fieldClass} mt-1">
							<input
								id="providers-{provider?.id}-auth-header"
								class={inputClass}
								bind:value={authHeader}
								placeholder="x-api-key"
								spellcheck="false"
							/>
						</div>
					</div>
				{/if}

				<div>
					<label
						class="text-[0.6875rem] text-gray-500 dark:text-gray-400"
						for="providers-{provider?.id}-prefix">{labelText('settings.admin.providers.prefix.label')}</label
					>
					<div class="{fieldClass} mt-1">
						<input
							id="providers-{provider?.id}-prefix"
							class={inputClass}
							bind:value={prefixId}
							placeholder="provider/"
							spellcheck="false"
						/>
					</div>
				</div>

				<div>
					<label class="text-[0.6875rem] text-gray-500 dark:text-gray-400" for="providers-{provider?.id}-notes"
						>{labelText('Notes')}</label
					>
					<div class="{fieldClass} mt-1">
						<input
							id="providers-{provider?.id}-notes"
							class={inputClass}
							bind:value={notes}
							placeholder={$i18n.t('Documentation URL')}
						/>
					</div>
				</div>
			</div>

			<div class="mt-2">
				<label class="text-[0.6875rem] text-gray-500 dark:text-gray-400" for="providers-{provider?.id}-models"
					>{labelText('settings.admin.providers.models.label')}</label
				>
				<textarea
					id="providers-{provider?.id}-models"
					class="mt-1 w-full resize-y rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 py-1.5 text-xs text-gray-700 outline-hidden transition-colors focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300 dark:focus:border-blue-500"
					rows="3"
					spellcheck="false"
					placeholder={'gpt-4o\nllama3.1:70b'}
					bind:value={modelText}></textarea>
				<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t('settings.admin.providers.models.description')}
				</p>
			</div>

			<div class="mt-2">
				<div class="flex items-center justify-between">
					<span class="text-[0.6875rem] text-gray-500 dark:text-gray-400">
						{$i18n.t('settings.admin.providers.headers.label')}
					</span>
					<button
						class="text-[0.6875rem] text-gray-500 transition hover:text-gray-800 dark:hover:text-gray-300"
						type="button"
						on:click={() => {
							headerRows = [...headerRows, { key: '', value: '' }];
						}}
					>
						{$i18n.t('Add')}
					</button>
				</div>

				<div class="mt-1 flex flex-col gap-1.5">
					{#each headerRows as row, index (index)}
						<div class="flex gap-1.5">
							<div class="{fieldClass} flex-1">
								<input
									class={inputClass}
									bind:value={row.key}
									placeholder="X-Request-Id"
									spellcheck="false"
								/>
							</div>
							<div class="{fieldClass} flex-[1.4]">
								<input class={inputClass} bind:value={row.value} placeholder="value" spellcheck="false" />
							</div>
							<button
								class="self-center p-1 text-gray-400 transition hover:text-red-500"
								type="button"
								aria-label={$i18n.t('Delete')}
								on:click={() => {
									headerRows = headerRows.filter((_, i) => i !== index);
								}}
							>
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-3.5">
									<path
										d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
									/>
								</svg>
							</button>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>

	<div class="mt-3 flex flex-wrap items-center gap-2">
		<button
			class="flex items-center gap-1 rounded-lg bg-gray-900 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-gray-700 disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
			type="button"
			disabled={saving || !baseUrl.trim() || (!dirty && !isNew)}
			on:click={save}
		>
			{$i18n.t('Save')}
		</button>

		<button
			class="flex items-center gap-1 rounded-lg border border-gray-100/60 px-2.5 py-1 text-xs transition hover:bg-gray-50 disabled:opacity-50 dark:border-white/[0.06] dark:hover:bg-white/[0.04]"
			type="button"
			disabled={testing || !baseUrl.trim()}
			on:click={test}
		>
			{$i18n.t('Test')}
		</button>

		<button
			class="rounded-lg px-2 py-1 text-xs text-gray-500 transition hover:bg-gray-50 dark:hover:bg-white/[0.04]"
			type="button"
			on:click={fetchModels}
		>
			{$i18n.t('settings.admin.providers.models.fetch.label')}
		</button>

		{#if !isNew}
			<button
				class="ml-auto rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:text-red-500"
				type="button"
				on:click={remove}
			>
				{$i18n.t('Delete')}
			</button>
		{:else}
			<button
				class="ml-auto rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:text-gray-700 dark:hover:text-gray-300"
				type="button"
				on:click={() => dispatch('cancel')}
			>
				{$i18n.t('Cancel')}
			</button>
		{/if}
	</div>

	{#if testResult}
		<p class="mt-2 text-[0.6875rem] text-green-600 dark:text-green-400">
			{$i18n.t('Connected')} · {testResult.count} {$i18n.t('Models').toLowerCase()} · {testResult.latency_ms} ms
		</p>
	{:else if testError}
		<p class="mt-2 text-[0.6875rem] text-red-500">{$i18n.t('Error')}: {testError}</p>
	{:else if provider?.has_key && !apiKey}
		<p class="mt-2 text-[0.6875rem] text-gray-400 dark:text-gray-600">
			{$i18n.t('settings.admin.providers.apiKey.description')}
		</p>
	{/if}
</div>
