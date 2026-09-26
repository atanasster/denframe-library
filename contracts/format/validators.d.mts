// Generated validator interfaces.
type Validator = ((data: unknown) => boolean) & { errors?: readonly unknown[] | null };
export const cardSettings: Validator;
export const definition: Validator;
export const ladder: Validator;
export const manifest: Validator;
export const overrides_calendar: Validator;
export const overrides_market: Validator;
export const overrides_news: Validator;
export const overrides_notes: Validator;
export const overrides_tasks: Validator;
export const overrides_weather: Validator;
export const packDefinition: Validator;
export const packManifest: Validator;
