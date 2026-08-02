(() => {
  document.body.classList.replace("no-js", "js");

  const toggle = document.querySelector("[data-nav-toggle]");
  const navigation = document.querySelector("#primary-navigation");

  if (!toggle || !navigation) {
    return;
  }

  const closeNavigation = (restoreFocus = false) => {
    toggle.setAttribute("aria-expanded", "false");
    navigation.classList.remove("is-open");
    if (restoreFocus) {
      toggle.focus();
    }
  };

  toggle.addEventListener("click", () => {
    const isOpen = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!isOpen));
    navigation.classList.toggle("is-open", !isOpen);
  });

  navigation.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => closeNavigation(true));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || toggle.getAttribute("aria-expanded") !== "true") {
      return;
    }

    closeNavigation();
    toggle.focus();
  });
})();
