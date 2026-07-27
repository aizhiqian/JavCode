export var CATALOG_PAGE_SIZE = 10;
export var ACTRESS_PAGE_SIZE = 20;
export var ACTRESS_INITIALS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

export var state = {
  movies: [],
  actresses: [],
  view: "catalog",
  selectedCode: null,
  filter: { q: "", actress: "", tag: "" },
  catalogPage: 1,
  actressPage: 1,
  actressInitial: "all",
  actressPinyinQ: "",
  auth: { configured: false, authenticated: false, username: "" },
  appReady: false,
};

export function $(sel) {
  return document.querySelector(sel);
}
