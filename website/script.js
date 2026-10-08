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

(() => {
  const section = document.querySelector("#quickstart");
  if (!section) {
    return;
  }

  const tabs = [...section.querySelectorAll('[role="tab"]')];
  const status = section.querySelector("[data-copy-status]");

  const report = (message, failed) => {
    status.textContent = message;
    status.classList.toggle("is-error", failed);
  };

  // Panels only become tab panels once tabs exist; without JavaScript they
  // stay plain stacked sections.
  tabs.forEach((tab) => {
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);
    panel.tabIndex = 0;
  });

  const selectTab = (tab, moveFocus = false) => {
    if (tab.getAttribute("aria-selected") !== "true") {
      report("", false);
    }
    tabs.forEach((candidate) => {
      const selected = candidate === tab;
      candidate.setAttribute("aria-selected", String(selected));
      candidate.tabIndex = selected ? 0 : -1;
      document.getElementById(candidate.getAttribute("aria-controls")).hidden = !selected;
    });
    if (moveFocus) {
      tab.focus();
    }
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      const last = tabs.length - 1;
      const target = {
        ArrowRight: index === last ? 0 : index + 1,
        ArrowLeft: index === 0 ? last : index - 1,
        Home: 0,
        End: last,
      }[event.key];
      if (target === undefined) {
        return;
      }
      event.preventDefault();
      selectTab(tabs[target], true);
    });
  });

  if (tabs.length) {
    // navigator.platform and userAgentData ignore user-agent overrides; the
    // user agent string is the one signal every browser reports consistently.
    const windowsTab = section.querySelector('[role="tab"][data-platform="windows"]');
    selectTab(/Windows/.test(navigator.userAgent) && windowsTab ? windowsTab : tabs[0]);
  }

  section.querySelectorAll("[data-copy-row]").forEach((row) => {
    const button = row.querySelector("button");
    const command = row.querySelector("[data-command]").textContent.trim();
    button.hidden = false;
    button.addEventListener("click", async () => {
      report("", false);
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) {
          throw new Error("Clipboard API unavailable");
        }
        await navigator.clipboard.writeText(command);
        report(`Copied: ${command}`, false);
      } catch {
        report("Couldn't copy — select the command and copy it manually.", true);
      }
    });
  });
})();
