import { Alert } from '../data/types';

/** Root stack: the tab app, plus pushed screens over it. */
export type RootStackParamList = {
  Tabs: undefined;
  AlertDetail: { alert: Alert };
  Evaluation: undefined;
  Strategies: undefined;
};
