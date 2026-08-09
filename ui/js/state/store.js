const initialState = {
  activeView: "chat",
  busy: false,
  health: null,
  messages: [
    {
      role: "agent",
      text: "Nisr is online. Give me an objective and I will plan, execute, verify, and report the result.",
      meta: { label: "Ready" },
    },
  ],
  lastRun: null,
  approvals: [],
  artifacts: [],
  audit: [],
};

class Store {
  #state = structuredClone(initialState);
  #listeners = new Set();

  get state() { return this.#state; }
  subscribe(listener) { this.#listeners.add(listener); return () => this.#listeners.delete(listener); }
  set(patch) { this.#state = { ...this.#state, ...patch }; this.#emit(); }
  update(updater) { this.#state = updater(this.#state); this.#emit(); }
  #emit() { for (const listener of this.#listeners) listener(this.#state); }
}

export const store = new Store();
