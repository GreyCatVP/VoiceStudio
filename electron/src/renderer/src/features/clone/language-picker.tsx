import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircleIcon, LanguagesIcon, XIcon } from 'lucide-react';
// Shared JSX controls are also consumed by the maintained shared UI modules.
// @ts-expect-error Shared JSX has no declaration file.
import LanguageFlag from '@shared/components/LanguageFlag';
import type { SearchOption } from '@/lib/language-search';
import { LANGUAGES } from '@/lib/languages';
import { languageOptions, languageSupported, type LanguageOption } from '@/lib/language-options';
import {
  canonicalLanguage,
  dialectOutcome,
  languageDialect,
  languageTagName,
} from '@/lib/language-variants';
import { setCloneSetting, useCloneSetting } from '@/lib/store/clone-settings';
import { LanguageMenu } from './language-menu';

export interface LanguagePickerProps {
  value?: string;
  onValueChange?: (value: string) => void;
  options?: string[];
  supportedOptions?: readonly string[] | null;
  disabled?: boolean;
  className?: string;
  modelLabel?: string;
  capabilityState?: 'known' | 'unknown' | 'loading' | 'error';
  recentsScope?: string;
  /** Regional accents the model renders itself (#3143); null = unknown. */
  renderedDialects?: readonly string[] | null;
}

export function LanguagePicker({
  value,
  onValueChange,
  options = LANGUAGES,
  supportedOptions,
  disabled = false,
  className,
  modelLabel,
  capabilityState,
  recentsScope = 'language',
  renderedDialects,
}: LanguagePickerProps = {}) {
  const { t, i18n } = useTranslation();
  const saved = useCloneSetting('language');
  // A value saved before the regional split ("Portuguese") shows as the
  // variant it means when this picker offers variants; the stored value
  // itself is left untouched (#3143). Pickers without variants (dub source)
  // keep showing it as-is.
  const raw = value ?? saved;
  const canonical = canonicalLanguage(raw);
  const language = canonical !== raw && options.includes(canonical) ? canonical : raw;
  const dialect = modelLabel ? languageDialect(language) : undefined;
  const outcome = dialectOutcome(dialect, renderedDialects);
  const dialectNote =
    outcome === 'voice' && dialect
      ? t('languagePicker.dialectFollowsVoice', {
          model: modelLabel,
          language: languageTagName(dialect.split('-')[0], i18n.language),
        })
      : outcome && typeof outcome === 'object'
        ? t('languagePicker.dialectUsed', {
            model: modelLabel,
            variant: languageTagName(outcome.used, i18n.language),
          })
        : '';
  const entries = useMemo(
    () =>
      languageOptions(options, i18n.language, t('languagePicker.auto')).map((option) => ({
        ...option,
        disabled: !languageSupported(option.value, supportedOptions),
      })),
    [options, i18n.language, t, supportedOptions],
  );
  const invalid = entries.some((option) => option.value === language && option.disabled);
  const unavailable = modelLabel
    ? t('languagePicker.unsupportedBy', { model: modelLabel })
    : t('languagePicker.unavailable');
  const renderOption = (entry: SearchOption) => {
    const option = entry as LanguageOption;
    return (
      <>
        {option.code ? (
          <LanguageFlag code={option.code === 'zh' ? 'cmn-Hans' : option.code} />
        ) : (
          <LanguagesIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        )}
        <span className="min-w-0 flex-1">
          <span className="block truncate leading-tight" title={option.label}>
            {option.label}
          </span>
          {option.native && option.native.toLowerCase() !== option.label.toLowerCase() && (
            <span
              className="block truncate text-[11px] leading-tight text-muted-foreground"
              lang={option.code}
            >
              {option.native}
            </span>
          )}
        </span>
        <span
          className="shrink-0 font-mono text-[10px] uppercase text-muted-foreground"
          aria-hidden="true"
        >
          {option.code}
        </span>
      </>
    );
  };
  return (
    <LanguageMenu
      value={language}
      options={entries}
      disabled={disabled}
      ariaLabel={t('clone.language')}
      buttonClassName={className}
      unavailableLabel={unavailable}
      recentsKey={`voicestudio.language-recents.${recentsScope}.v1`}
      onChange={(next) => {
        if (onValueChange) onValueChange(next);
        else setCloneSetting('language', next);
      }}
      renderOption={renderOption}
      renderValue={(entry) => {
        const option = entry as LanguageOption | undefined;
        return (
          <>
            {invalid ? (
              <AlertCircleIcon className="size-4 text-warning" aria-hidden="true" />
            ) : option?.code ? (
              <LanguageFlag code={option.code === 'zh' ? 'cmn-Hans' : option.code} />
            ) : (
              <LanguagesIcon className="size-4 text-muted-foreground" aria-hidden="true" />
            )}
            <span className="max-w-48 truncate">{option?.label || language}</span>
          </>
        );
      }}
      header={
        <span className="min-w-0 truncate" title={modelLabel}>
          {modelLabel || t('clone.language')}
          {capabilityState && capabilityState !== 'known'
            ? ` · ${t(`languagePicker.${capabilityState}`)}`
            : ''}
        </span>
      }
      footer={
        modelLabel ? (
          <div className="space-y-1">
            {dialectNote && <p role="status">{dialectNote}</p>}
            <div className="flex items-center justify-between gap-2">
              <span>
                {invalid ? t('languagePicker.chooseSupported') : t('languagePicker.modelLanguages')}
              </span>
              <a
                href="#/settings/models/tts"
                className="shrink-0 rounded text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring"
              >
                {t('languagePicker.changeModel')}
              </a>
            </div>
          </div>
        ) : undefined
      }
    />
  );
}

export function MultiLanguagePicker({
  selected,
  onChange,
  options = LANGUAGES,
  supportedOptions,
  disabled = false,
}: {
  selected: string[];
  onChange: (selected: string[]) => void;
  options?: string[];
  supportedOptions?: readonly string[] | null;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const available = options.filter((language) => !selected.includes(language));
  return (
    <div className="space-y-2">
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((language) => (
            <span
              key={language}
              className="inline-flex h-7 max-w-full items-center gap-1 rounded-full bg-primary/10 px-2 text-xs font-medium text-primary"
            >
              <span className="truncate">{language}</span>
              <button
                type="button"
                disabled={disabled}
                aria-label={`${t('common.delete')} ${language}`}
                className="flex size-6 shrink-0 items-center justify-center rounded-full hover:bg-primary/15 focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                onClick={() => onChange(selected.filter((item) => item !== language))}
              >
                <XIcon className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      {available.length > 0 && (
        <LanguagePicker
          value={t('dub.manage_languages')}
          options={available}
          supportedOptions={supportedOptions}
          recentsScope="dub"
          disabled={disabled}
          onValueChange={(language) => onChange([...selected, language])}
        />
      )}
    </div>
  );
}
