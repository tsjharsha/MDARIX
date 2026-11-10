import { Panel } from "../../admin/console/charts";
import { errorText, useResource } from "../../customer-admin/shared";
import type { Trees } from "../decisionTrees";
import { useRuleRegister, useTabParam } from "../workspaceContext";
import { RuleRegister } from "./RuleRegister";
import { TreeAnswer } from "./TreeAnswer";
import { TreeEdit } from "./TreeEdit";

export { TREE_NAMES, treePlace, type TreeMarket, type TreeNode, type TreePath, type Trees } from "../decisionTrees";

/**
 * Decision trees (0.10.75, Release C part C3; the questionnaire itself from 0.10.83, D2): one tree per market, built
 * from the decision guides (their locked wording and test matrix). A complaint is answered on its market's tree, and
 * the outcome and Sign sit beside it. The address carries the market and the complaint
 * (/app/decision-trees?market=US&complaint=<id>), so a complaint's page opens its tree.
 */
export function DecisionTreesSection() {
  const all = useResource<Trees>("/api/v1/decision-trees");
  const [mode, setMode] = useTabParam("mode");
  const register = useRuleRegister();
  if (!all.data)
    return (
      // The page head asks the question (0.10.87): while the trees load the panel says only that.
      <Panel title="Reading the trees…" source={all}>
        {all.state === "error" && <p className="ac-muted">{errorText(all.error, "The trees could not be read.")}</p>}
      </Panel>
    );
  const edit = mode === "edit";
  // B4: the read-only Rules tab, for every signed-in member, while the rule register is on.
  const rules = register && mode === "rules";
  const modes = (
    <div className="dt-modes" role="group" aria-label="Mode">
      <button type="button" aria-pressed={!edit && !rules} onClick={() => setMode(null)}>
        Answer
      </button>
      <button type="button" aria-pressed={edit} onClick={() => setMode("edit")}>
        Edit this tree
      </button>
      {register && (
        <button type="button" aria-pressed={rules} onClick={() => setMode("rules")}>
          Rules
        </button>
      )}
    </div>
  );
  // While answering, the mode switch sits on the market row (0.10.84): the questions and Sign start higher.
  return (
    <div className="dt-page">
      {rules ? (
        <>
          {modes}
          <RuleRegister />
        </>
      ) : edit ? (
        <>
          {modes}
          <TreeEdit trees={all.data} />
        </>
      ) : (
        <TreeAnswer trees={all.data} modes={modes} />
      )}
    </div>
  );
}
