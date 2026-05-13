# Transition Rule Syntax

The **Rule** column in the Transitions sheet defines when a target species becomes active or reaches a specific level. Rules are Boolean or multi-valued expressions over species identifiers.

## Operators

### Logical Operators

| Operator | Meaning | Precedence  |
| -------- | ------- | ----------- |
| `!`    | NOT     | 1 (highest) |
| `&`    | AND     | 2           |
| `^`    | XOR     | 3           |
| `\|`    | OR      | 4 (lowest)  |

Use parentheses `()` to override precedence.

### Operator Precedence

Higher-precedence operators bind more tightly. Comparison operators (`>=`, `<`, etc.) bind tightest and form atomic terms; then NOT, AND, XOR, OR from high to low. All binary operators are **left-associative**, so chains of the same operator group left-to-right.

| Expression         | Parsed as            |
| ------------------ | -------------------- |
| `A & B \| C`      | `(A & B) \| C`      |
| `A \| B & C`      | `A \| (B & C)`      |
| `A ^ B & C`       | `A ^ (B & C)`       |
| `A & B ^ C \| D`  | `((A & B) ^ C) \| D` |
| `!A & B`          | `(!A) & B`          |
| `A >= 2 & B`      | `(A >= 2) & B`      |
| `A & B & C`       | `(A & B) & C`       |

When in doubt, use parentheses: `(A & B) | C` is always unambiguous.

### Comparison Operators

Used in multi-valued models where species levels can exceed 1:

| Operator    | Example    | Meaning                        |
| ----------- | ---------- | ------------------------------ |
| `>=`      | `A >= 2` | level of A is at least 2       |
| `>`       | `A > 1`  | level of A is strictly above 1 |
| `<`       | `A < 2`  | level of A is below 2          |
| `<=`      | `A <= 1` | level of A is at most 1        |
| `=`, `==` | `A == 2` | level of A is exactly 2        |
| `!=`      | `A != 0` | level of A is not 0            |

### Constants

| Value                       | Meaning                            |
| --------------------------- | ---------------------------------- |
| `TRUE`                    | Always active (constant 1)         |
| `FALSE`                   | Always inactive (constant 0)       |
| Integer (`2`, `3`, ...) | Fixed at that level (multi-valued) |

## Compact Colon Notation

An alternative compact format for threshold expressions. Colon notation is always accepted as input; the `--colon-format` flag controls whether the tool *outputs* colon notation (instead of `>=`/`<`) when converting SBML to a spreadsheet.

| Colon    | Operator equivalent       |
| -------- | ------------------------- |
| `A`    | `A >= 1` (A is active)  |
| `A:2`  | `A >= 2`                |
| `!A`   | `A < 1` (A is inactive) |
| `!A:2` | `A < 2`                 |

Colon notation is shorthand: `A:N` always means `A >= N`, and `!A:N` always means `A < N`. All other logical operators (`&`, `|`, `^`, `!`, parentheses) work the same in both formats.

## Examples

| Rule                   | Meaning                                                              |
| ---------------------- | -------------------------------------------------------------------- |
| `A`                  | active when A is active (level >= 1)                                 |
| `A & B`              | active when both A and B are active                                  |
| `A \| B`              | active when at least one is active                                   |
| `!A`                 | active when A is inactive (level 0)                                  |
| `A & !B`             | active when A is active and B is inactive                            |
| `A ^ B`              | active when exactly one of A or B is active (XOR)                    |
| `(A \| B) & C`        | active when C is active and at least one of A, B is active           |
| `A >= 2 & !B`        | active when A is at level 2+ and B is inactive                       |
| `N & !CI:2 & !Cro:3` | N active AND CI below level 2 AND Cro below level 3 (colon notation) |

## Multi-valued Models

In multi-valued (non-Boolean) models, species can have levels from 0 up to their `MaxLevel` (set in the Species sheet). The Transitions sheet encodes the update function using the **Level** and **Rule** columns together.

### How it works

Each row in the Transitions sheet describes one condition under which the target reaches a specific level:

| Target | Level | Rule           |
| ------ | ----- | -------------- |
| A      | 2     | `B >= 2 & C` |
| A      | 1     | `B >= 1`     |

This means: A reaches level 2 when B >= 2 and C is active; A reaches level 1 when B >= 1. The default (when no rule matches) is level 0.

Multiple rows for the **same target** with **different Level values** together define the multi-valued update function. During conversion to SBML-qual, these become separate `<functionTerm>` elements within a single `<transition>`, each with its own `resultLevel`.

When the Level column is empty (or absent), the model is treated as Boolean. Each target has a single rule that determines whether it is active (level 1) or inactive (level 0, the default).

### How the tool converts

**SBML → Spreadsheet**: Each `<functionTerm>` with `resultLevel > 0` in a transition becomes a separate row. If a transition has multiple function terms, the transition ID gets a level suffix (e.g., `tr_Cro_2`, `tr_Cro_1`). The `<defaultTerm>` (typically `resultLevel="0"`) does not generate a row.

**Spreadsheet → SBML**: Rows sharing the same Target are grouped into a single `<transition>`. Each row's Level becomes a `<functionTerm>` with the corresponding `resultLevel`. A `<defaultTerm>` with `resultLevel="0"` is added automatically.

### Example: 3-level species

For a species `Cro` with `MaxLevel = 3`:

| Target | Level | Rule       |
| ------ | ----- | ---------- |
| Cro    | 3     | `CI < 1` |
| Cro    | 2     | `CI < 2` |
| Cro    | 1     | `CI < 3` |

This encodes: Cro = 3 when CI is at level 0; Cro = 2 when CI is below level 2; Cro = 1 when CI is below level 3; otherwise Cro = 0.

The equivalent colon notation:

| Target | Level | Rule      |
| ------ | ----- | --------- |
| Cro    | 3     | `!CI`   |
| Cro    | 2     | `!CI:2` |
| Cro    | 1     | `!CI:3` |

## Threshold Handling

When importing SBML-qual files, TabularQual follows the SBML Level 3 Qualitative Models specification (section 5.1, Best practices — Logical Regulatory Networks):

> The thresholdLevel, when specified, indicates the level at which the species participates in the transition. Any reference to the Input id attribute in a `<ci>` element within a functionTerm of the transition refers to the value of this thresholdLevel.

In TabularQual converter:

1. **Collects threshold mappings**: For each input in a transition, the tool maps the input's `id` attribute to its `thresholdLevel` value (e.g., `theta_t9_ex` → `1` from the example below).
2. **Substitutes in MathML**: When converting the MathML expression, any `<ci>` referencing an input `id` (rather than a species) is replaced with the numeric threshold value.
3. **Simplifies for Boolean**: Comparisons against 0 or 1 are simplified since Boolean models can only take 0 or 1:

| Expression              | Simplified | Reasoning                 |
| ----------------------- | ---------- | ------------------------- |
| `A > 0`, `A >= 1`  | `A`      | level > 0 means active   |
| `A < 1`, `A <= 0`  | `!A`     | level > 1 means inactive |
| `A == 1`, `A != 0` | `A`      | active                    |
| `A == 0`, `A != 1` | `!A`     | inactive                  |

Comparisons against other threshold values (e.g., `A >= 2`) are kept as-is.

### Example

Given the SBML-qual input for transition `t9` (target: `ikb`) from [BIOMD0000000562](../test/BIOMD0000000562_url.xml):

```xml
<qual:input qual:id="theta_t9_ikk" qual:qualitativeSpecies="ikk"
            qual:thresholdLevel="1"/>
<qual:input qual:id="theta_t9_ex"  qual:qualitativeSpecies="ex"
            qual:thresholdLevel="1"/>
```

The MathML expression `ex >= theta_t9_ex | ikk < theta_t9_ikk` is processed as:

1. Substitute: `ex >= 1 | ikk < 1`
2. Simplify: `ex | !ikk`

This behavior is consistent with [BoolNet](https://cran.r-project.org/package=BoolNet) `loadSBML` function.
