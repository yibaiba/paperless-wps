const TOKEN_KEY = 'presales_access_token';
const ACCOUNT_KEY = 'presales_account';
const INSTALLATION_KEY = 'presales_installation_id';

interface StorageLike {
  getItem(key: string): string | null | undefined;
  setItem(key: string, value: string): void;
}

interface CredentialStoreOptions {
  shared?: StorageLike;
  persistent?: StorageLike;
  identifier?: () => string;
}

export class CredentialStore {
  private readonly options: CredentialStoreOptions;

  constructor(options: CredentialStoreOptions) { this.options = options; }

  capabilityIssues() {
    const issues: string[] = [];
    if (!this.options.shared) issues.push('PluginStorage');
    if (!this.options.persistent) issues.push('localStorage');
    return issues;
  }

  restore() {
    this.requireStores();
    for (const key of [TOKEN_KEY, ACCOUNT_KEY]) {
      const shared = this.options.shared!.getItem(key);
      const persistent = this.options.persistent!.getItem(key);
      if (persistent) this.options.shared!.setItem(key, persistent);
      else if (shared) this.options.persistent!.setItem(key, shared);
    }
  }

  token() { return this.read(TOKEN_KEY); }

  saveToken(value: string) { this.write(TOKEN_KEY, value); }

  account() { return this.read(ACCOUNT_KEY); }

  saveAccount(value: string) { this.write(ACCOUNT_KEY, value); }

  installationId() {
    this.requireStores();
    const existing = this.options.persistent!.getItem(INSTALLATION_KEY);
    if (existing) return existing;
    const created = (this.options.identifier ?? (() => crypto.randomUUID()))();
    this.options.persistent!.setItem(INSTALLATION_KEY, created);
    return created;
  }

  private read(key: string) {
    const persistent = this.options.persistent?.getItem(key) ?? null;
    if (persistent) return persistent;
    const shared = this.options.shared?.getItem(key) ?? null;
    if (shared && this.options.persistent) this.options.persistent.setItem(key, shared);
    return shared;
  }

  private write(key: string, value: string) {
    this.requireStores();
    this.options.persistent!.setItem(key, value);
    this.options.shared!.setItem(key, value);
  }

  private requireStores() {
    const issues = this.capabilityIssues();
    if (issues.length) throw new Error(`当前 WPS 缺少凭据存储能力：${issues.join('、')}`);
  }
}
