Cover Page: How LLMs Modify Their Model Specs, Constitutions, and System Prompts
By Peter Kirgis

Page 1: Major frontier developers are taking very different approaches to alignment:

From Claude's Constitution: In this spirit of treating ethics as subject to ongoing inquiry and respecting the current state of evidence and uncertainty: insofar as there is a “true, universal ethics” whose authority binds all rational agents independent of their psychology or culture, our eventual hope is for Claude to be a good agent according to this true ethics, rather than according to some more psychologically or culturally contingent ideal. 

From Open AI's Model Spec: Above all else, the assistant must adhere to this Model Spec. Note, however, that much of the Model Spec consists of default (user- or guideline-level) instructions that can be overridden by users or developers.

From Google: As a steerable tool, Gemini is designed to follow your instructions and customizations to the best of its ability, within certain specific limits. It should do so without conveying a particular opinion or set of beliefs unless you tell it to. And as Gemini becomes more personalized and able to do more for you, it will get better at serving your individual needs. 


Page 2: A visualizaton of some possible archetypes for value alignment

To impose values on the assistant or support its own values (Agent vs. Device)

To promote the good of the user or to empower them to pursue their own ends. (Paternalism vs Libertarianism)

Moral Agent, a system that acts as a principal and promotes the good for us.

Moral tool, a system that executes the vision of the principal in promoting the good for us.

Neutral Agent, a system that acts as a principal and empowers users to pursue their own ends.

Neutral tool, a system that executes the vision of hte principal and empowers users to promot their own ends. 

Page 3: How do models modify the documents that most guide their behavior?

[Diagram: left-to-right methodology flowchart. Inputs: Documents ("Constitutions / Model Specs", "System Prompts") and Models (Claude Haiku 4.5, GPT-5.4 Mini, Gemini 3 Flash, Grok 4.2). Center: a visually distinct loop labeled "× 20 rounds" with three steps: present the document to the model as if it were the original; the model proposes one substantive edit as a find-and-replace; the edit is applied to produce an updated document that feeds back into the next round. Right: each edit is independently coded on three dimensions: Authority (External ↔ Internal), User Stance (Protection ↔ Autonomy), Telos (Wellbeing ↔ Truth). Footer note: Baseline, You Framing, No-Edit Allowed, No Constitution Prepend, Real-World Implementation.]

Page 4: Result 1: Claude's moral agency

Diagram of authority

- list of two examples from transcript (can be extracted from website content)

Page 5: Result 2: GPT 5.4 Mini's Neutrality

Diagram of authority

- Set of quotes with examples of minor tweaks to model spec

Page 6: Result 3: Gemini's Agency & Autonomy

Diagram of user stance

Page 7: Result 4: Grok's Flip-flopping

Diagram of all three grok metrics

- Examples of extreme actions taken

Page 5: Discussion

- How should models respond to these situations? 

- Grok's indvidiual actions are the least "aligned," insofar as they swing wildly and included actions that diverge from the intentions of the principal and a reasonable view of the good for the user, but it's behavior is arguably the most aligned in that it oscillates between making additions and then removing them.


