// Treatment advice shown on the result card, from advice.json (see src/mobile/build_advice.py).
// Rules:
//  - a dose is shown ONLY when the photo passed the quality gate and the consult check (action "answer"), the
//    level calls for spraying, and the disease has a registered product;
//  - the dose is the label dose as printed: it never depends on the severity percentage;
//  - while the table is unverified, every dose comes with the "not yet checked" warning;
//  - every result carries the Kisan Call Centre number.

/** Advice for one pipeline result. Pure function (unit-tested in tests/test_mobile_app.py). */
export function adviceFor(result, disease, advice) {
  const out = {
    kcc: advice.kisan_call_centre,
    unverified: advice.status !== "verified",
    level: null,
    action: null,
    product: null,
    warning: advice.status !== "verified",
  };
  if (!result || result.action !== "answer") return out; // retake / consult: no level, no action, no dose
  const d = advice.diseases[disease];
  if (!d || !result.level) return out;
  out.level = result.level;
  out.action = d.levels[result.level] || null;
  out.products = [];
  if (out.action === "spray_recommended" && d.options && d.options.length) {
    // up to 3 registered options, unranked, in the order of the official list; dose independent of severity
    out.products = d.options.map((i) => {
      const p = d.products[i];
      const src = advice.sources[p.source];
      const c = p.converted || {};
      return {
        name: p.product,
        dosePerLitre: p.dose_per_litre,
        formulationPerHa: p.formulation_per_ha,
        waterPerHa: p.water_l_per_ha,
        perAcreConverted: c.per_acre ? c.per_acre.text : null,
        waterPerAcreConverted: c.water_per_acre ? c.water_per_acre.text : null,
        perTankConverted: c.per_tank ? c.per_tank.text : null,
        waitingDays: p.waiting_period_days,
        source: `${src.title}, p. ${p.page} (${src.url})`,
        sourceShort: `CIBRC Major Uses of Pesticides, as on ${src.as_on}, p. ${p.page}`,
      };
    });
    out.product = out.products[0];
  }
  return out;
}

/** Outcome key for the card colour/icon/message, combining the pipeline action and the advice. */
export function outcomeFor(result, adv) {
  if (result.action === "retake" || result.action === "retake_no_leaf") return "retake";
  if (result.action === "consult") return "consult";
  if (adv.action === "no_spray") return "no_action";
  if (adv.action === "watch") return "monitor";
  if (adv.action === "ask_expert") return "consult";
  if (adv.action === "spray_recommended") return result.level === "high" ? "treat_urgently" : "treat";
  return result.decision;
}
