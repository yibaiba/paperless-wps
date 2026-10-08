import type { Configuration } from "../types";

const configurationKeys = new WeakMap<Configuration, string>();
const businessKeys = new WeakMap<Configuration, string>();

export function configurationKey(configuration: Configuration) {
  const cached = configurationKeys.get(configuration);
  if (cached !== undefined) return cached;
  const value = JSON.stringify(configuration);
  configurationKeys.set(configuration, value);
  return value;
}

export function businessKey(configuration: Configuration) {
  const cached = businessKeys.get(configuration);
  if (cached !== undefined) return cached;
  const { drawing_xml: _drawing, ...business } = configuration;
  const value = JSON.stringify(business);
  businessKeys.set(configuration, value);
  return value;
}
