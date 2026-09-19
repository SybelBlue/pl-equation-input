(() => {
  const relationShortcuts = {
    '<=': '\\le',
    '>=': '\\ge',
  };
  const relationKeyboardRow = [
    { latex: '=', width: 2 },
    {
      latex: '<',
      shift: { latex: '\\le' },
    },
    {
      latex: '>',
      shift: { latex: '\\ge' },
    },
  ];
  const navigationKeycaps = {
    '[left]': {
      class: 'hide-shift',
      latex: '\\leftarrow',
      command: 'performWithFeedback(moveToPreviousChar)',
      shift: {
        latex: '\\Leftarrow',
        command: 'performWithFeedback(extendSelectionBackward)',
      },
    },
    '[right]': {
      class: 'hide-shift',
      latex: '\\rightarrow',
      command: 'performWithFeedback(moveToNextChar)',
      shift: {
        latex: '\\Rightarrow',
        command: 'performWithFeedback(extendSelectionForward)',
      },
    },
  };

  const customizeEquationKeyboard = () => {
    const layouts = window.mathVirtualKeyboard.layouts;
    const mathLayout = layouts[0];
    if (typeof mathLayout === 'string' || !Array.isArray(mathLayout?.rows)) {
      return;
    }

    let updated = false;
    for (const row of mathLayout.rows) {
      for (const [index, keycap] of row.entries()) {
        if (typeof keycap !== 'object' || keycap === null || !('label' in keycap)) {
          continue;
        }
        const replacement = navigationKeycaps[keycap.label];
        if (replacement) {
          row[index] = replacement;
          updated = true;
        }
      }
    }

    if (!mathLayout.rows.includes(relationKeyboardRow)) {
      mathLayout.rows.push(relationKeyboardRow);
      updated = true;
    }

    if (updated) {
      window.mathVirtualKeyboard.layouts = layouts;
    }
  };

  const combineRelationShortcut = (mathField, event) => {
    if (
      event.key !== '=' ||
      event.defaultPrevented ||
      event.isComposing ||
      event.ctrlKey ||
      event.metaKey ||
      event.altKey ||
      !mathField.selectionIsCollapsed
    ) {
      return;
    }

    const position = mathField.selection.ranges[0][0];
    if (position === 0) {
      return;
    }

    const previous = mathField.getValue(position - 1, position, 'latex');
    const replacement = { '<': '\\le', '>': '\\ge' }[previous];
    if (!replacement) {
      return;
    }

    event.preventDefault();
    mathField.selection = { ranges: [[position - 1, position]] };
    mathField.insert(replacement, {
      format: 'latex',
      insertionMode: 'replaceSelection',
      selectionMode: 'after',
    });
  };

  const combineInsertedRelation = (mathField) => {
    if (!mathField.selectionIsCollapsed) {
      return;
    }

    const position = mathField.selection.ranges[0][0];
    if (position < 2 || mathField.getValue(position - 1, position, 'latex') !== '=') {
      return;
    }

    const previous = mathField.getValue(position - 2, position - 1, 'latex');
    const replacement = { '<': '\\le', '>': '\\ge' }[previous];
    if (!replacement) {
      return;
    }

    mathField.selection = { ranges: [[position - 2, position]] };
    mathField.insert(replacement, {
      format: 'latex',
      insertionMode: 'replaceSelection',
      selectionMode: 'after',
    });
  };

  window.PLEquationInput = function (name) {
    window.PLSymbolicInput(name);

    const mathField = document.getElementById(`symbolic-input-${name}`);
    const shortcuts = mathField.inlineShortcuts;
    Object.assign(shortcuts, relationShortcuts);
    mathField.inlineShortcuts = shortcuts;

    // The vendored initializer installs its math layout first, so this listener
    // runs afterward and customizes the active equation field's layout only.
    mathField.addEventListener('focus', customizeEquationKeyboard);
    mathField.addEventListener('keydown', (event) => combineRelationShortcut(mathField, event), {
      capture: true,
    });
    mathField.addEventListener('input', () => combineInsertedRelation(mathField));
  };
})();
