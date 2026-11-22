import { WEBUI_API_BASE_URL } from '$lib/constants';

export type ProviderKind = 'openai' | 'anthropic' | 'gemini' | 'ollama' | 'custom';
export type ProviderAuthStyle = 'bearer' | 'header' | 'none';

export type Provider = {
	id: string;
	name: string;
	kind: ProviderKind;
	base_url: string;
	api_key?: string;
	api_key_masked?: string;
	has_key?: boolean;
	auth_style: ProviderAuthStyle;
	auth_header: string;
	model_ids: string[];
	headers: Record<string, string>;
	prefix_id: string;
	enabled: boolean;
	notes: string;
	created_at?: number;
	updated_at?: number;
};

export type ProviderDraft = Omit<
	Provider,
	'id' | 'created_at' | 'updated_at' | 'api_key_masked' | 'has_key'
> & {
	// `undefined` keeps the stored token, `''` clears it.
	api_key?: string;
};

export type ProvidersState = {
	applied_at?: number;
	openai_connections?: number;
	ollama_connections?: number;
	provider_count?: number;
};

export type ProvidersResponse = {
	providers: Provider[];
	kinds?: ProviderKind[];
	auth_styles?: ProviderAuthStyle[];
	state?: ProvidersState;
};

export type ProviderTestResult = {
	status: string;
	models: string[];
	count: number;
	latency_ms: number;
};

/** Thin client for the fork's `/api/v1/providers` router. */
const request = async <T = unknown>(path: string, options: RequestInit, token = ''): Promise<T> => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/providers/${path}`.replace('//?', '/?'), {
		...options,
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` }),
			...(options.headers ?? {})
		}
	});

	if (!res.ok) {
		const detail = await res
			.json()
			.then((data) => data?.detail ?? data)
			.catch(() => res.statusText);

		throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
	}

	if (res.status === 204) {
		return null as unknown as T;
	}

	return res.json();
};

export const getProviders = async (token: string = '', reveal = false) =>
	request<ProvidersResponse>(`?reveal=${reveal}`, { method: 'GET' }, token);

export const createProvider = async (token: string, provider: ProviderDraft) =>
	request<Provider>('', { method: 'POST', body: JSON.stringify(provider) }, token);

export const updateProvider = async (token: string, id: string, provider: ProviderDraft) =>
	request<Provider>(`${id}`, { method: 'PUT', body: JSON.stringify(provider) }, token);

export const deleteProvider = async (token: string, id: string) =>
	request<{ status: boolean }>(`${id}`, { method: 'DELETE' }, token);

export const testProvider = async (token: string, id: string) =>
	request<ProviderTestResult>(`${id}/test`, { method: 'POST' }, token);

export const saveProviderModels = async (token: string, id: string, save = true) =>
	request<{ models: string[]; count: number; saved: boolean }>(`${id}/models?save=${save}`, { method: 'POST' }, token);

export const testProviderDraft = async (token: string, draft: Partial<ProviderDraft>) =>
	request<ProviderTestResult>('preview/test', { method: 'POST', body: JSON.stringify(draft) }, token);

export const applyProviders = async (token: string) =>
	request<{ status: boolean } & ProvidersState>('apply', { method: 'POST' }, token);
