import { state } from "./state.js";
import { api } from "./api.js";

/** Items for one label kind from the shared library index cache. */
export function getLibraryLabelItems(kind) {
  if (kind === "categories") return state.labels.categories || [];
  return state.labels.tags || [];
}

/**
 * Canonical loader for the shared label index cache (state.labels).
 * Used by the labels page and the detail editor suggestions.
 */
export function loadLibraryLabels() {
  return api("/api/labels").then(function (data) {
    state.labels = {
      categories: data.categories || [],
      tags: data.tags || [],
    };
    return state.labels;
  });
}
