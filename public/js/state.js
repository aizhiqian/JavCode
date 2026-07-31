export var CATALOG_PAGE_SIZE = 10;
export var ACTRESS_PAGE_SIZE = 20;

export var state = {
  movies: [],
  /** filterKey last successfully loaded into movies; null = need fetch. */
  moviesFilterKey: null,
  actresses: [],
  view: "catalog",
  selectedCode: null,
  filter: { q: "", actress: "", tag: "" },
  catalogPage: 1,
  actressPage: 1,
  actressInitial: "all",
  actressPinyinQ: "",
  labels: { categories: [], tags: [] },
  labelInitial: "all",
  labelPinyinQ: "",
  auth: { configured: false, authenticated: false, username: "" },
  appReady: false,
};

export function $(sel) {
  return document.querySelector(sel);
}

/** Drop in-memory catalog rows so the next catalog entry refetches. */
export function invalidateCatalog() {
  state.movies = [];
  state.moviesFilterKey = null;
}
