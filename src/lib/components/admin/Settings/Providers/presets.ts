import type { ProviderAuthStyle, ProviderDraft, ProviderKind } from '$lib/apis/providers';

export type ProviderPreset = {
	id: string;
	name: string;
	kind: ProviderKind;
	base_url: string;
	auth_style: ProviderAuthStyle;
	auth_header: string;
	docs: string;
	hint: string;
};

/** Starters for "Add provider": link, API shape and docs of popular endpoints. */
export const PROVIDER_PRESETS: ProviderPreset[] = [
	{
		id: 'openai',
		name: 'OpenAI',
		kind: 'openai',
		base_url: 'https://api.openai.com/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://platform.openai.com/docs/api-reference',
		hint: 'sk-…'
	},
	{
		id: 'anthropic',
		name: 'Anthropic',
		kind: 'anthropic',
		base_url: 'https://api.anthropic.com/v1',
		auth_style: 'header',
		auth_header: 'x-api-key',
		docs: 'https://docs.anthropic.com/en/api/messages',
		hint: 'sk-ant-…'
	},
	{
		id: 'google-gemini',
		name: 'Google Gemini',
		kind: 'gemini',
		base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://ai.google.dev/gemini-api/docs/openai',
		hint: 'AIza…'
	},
	{
		id: 'deepseek',
		name: 'DeepSeek',
		kind: 'openai',
		base_url: 'https://api.deepseek.com/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://api-docs.deepseek.com',
		hint: 'sk-…'
	},
	{
		id: 'mistral',
		name: 'Mistral',
		kind: 'openai',
		base_url: 'https://api.mistral.ai/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://docs.mistral.ai/api',
		hint: '…'
	},
	{
		id: 'groq',
		name: 'Groq',
		kind: 'openai',
		base_url: 'https://api.groq.com/openai/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://console.groq.com/docs/api-reference',
		hint: 'gsk_…'
	},
	{
		id: 'openrouter',
		name: 'OpenRouter',
		kind: 'openai',
		base_url: 'https://openrouter.ai/api/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://openrouter.ai/docs/api-reference',
		hint: 'sk-or-…'
	},
	{
		id: 'xai',
		name: 'xAI (Grok)',
		kind: 'openai',
		base_url: 'https://api.x.ai/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://docs.x.ai/api-reference',
		hint: '…'
	},
	{
		id: 'together',
		name: 'Together AI',
		kind: 'openai',
		base_url: 'https://api.together.xyz/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://docs.together.ai/reference',
		hint: '…'
	},
	{
		id: 'fireworks',
		name: 'Fireworks',
		kind: 'openai',
		base_url: 'https://api.fireworks.ai/inference/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://docs.fireworks.ai/api-reference',
		hint: '…'
	},
	{
		id: 'azure',
		name: 'Azure OpenAI',
		kind: 'openai',
		base_url: 'https://YOUR-RESOURCE.openai.azure.com/openai/v1',
		auth_style: 'bearer',
		auth_header: 'api-key',
		docs: 'https://learn.microsoft.com/azure/ai-services/openai/reference',
		hint: 'api-key header'
	},
	{
		id: 'ollama',
		name: 'Ollama',
		kind: 'ollama',
		base_url: 'http://localhost:11434',
		auth_style: 'none',
		auth_header: 'Authorization',
		docs: 'https://docs.ollama.com/api',
		hint: 'no key needed'
	},
	{
		id: 'lmstudio',
		name: 'LM Studio',
		kind: 'custom',
		base_url: 'http://localhost:1234/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://docs.lmstudio.ai',
		hint: 'optional'
	},
	{
		id: 'llamacpp',
		name: 'llama.cpp server',
		kind: 'custom',
		base_url: 'http://localhost:8080/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://github.com/ggml-org/llama.cpp',
		hint: 'optional'
	},
	{
		id: 'vllm',
		name: 'vLLM',
		kind: 'custom',
		base_url: 'http://localhost:8000/v1',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: 'https://docs.vllm.ai/en/latest/api/openai_compat.html',
		hint: 'optional'
	},
	{
		id: 'custom',
		name: 'Custom',
		kind: 'custom',
		base_url: '',
		auth_style: 'bearer',
		auth_header: 'Authorization',
		docs: '',
		hint: 'https://my-endpoint.example/v1'
	}
];

export const getPreset = (id: string): ProviderPreset | undefined =>
	PROVIDER_PRESETS.find((preset) => preset.id === id);

export const providerFromPreset = (preset: ProviderPreset): ProviderDraft => ({
	name: preset.name,
	kind: preset.kind,
	base_url: preset.base_url,
	api_key: '',
	auth_style: preset.auth_style,
	auth_header: preset.auth_header || 'Authorization',
	model_ids: [],
	headers: {},
	prefix_id: '',
	enabled: true,
	notes: preset.docs
});

export const PROVIDER_KIND_LABELS: Record<ProviderKind, string> = {
	openai: 'OpenAI compatible',
	anthropic: 'Anthropic',
	gemini: 'Google Gemini',
	ollama: 'Ollama',
	custom: 'Custom'
};

export const AUTH_STYLE_LABELS: Record<ProviderAuthStyle, string> = {
	bearer: 'Authorization: Bearer …',
	header: 'Custom header',
	none: 'No auth'
};
