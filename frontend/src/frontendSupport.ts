export interface FrontendStatusModel {
  frontend_support_timestamp: string | null;
  frontend_saas_available: boolean;
}

export type FrontendSupportStatus = 'full' | 'frontend_only' | 'saas_only' | 'not_found';

export function getFrontendSupportStatus(
  model: FrontendStatusModel
): FrontendSupportStatus {
  if (model.frontend_support_timestamp && model.frontend_saas_available) {
    return 'full';
  }
  if (model.frontend_support_timestamp) {
    return 'frontend_only';
  }
  if (model.frontend_saas_available) {
    return 'saas_only';
  }
  return 'not_found';
}
