# Quantum Cryptography Talk — Speaker Notes

**Length:** 35 minutes • **Slides you're presenting:** 10 (1–10) • **Skipping:** 11–12 (IA closer)
**Average pace:** ~3:30 per slide. Dense originals get ~4 min, image breathers get ~2 min.

A note on tone before you start: humor in a technical talk works best when it's small and dry, not stand-up. Don't push for laughs. Land one good line per slide and move on. The audience will trust you more if you sound like you find this stuff *interesting* than if you sound like you're trying to entertain them.

---

## 🎤 INTRO — Introduce Yourself (~1:30)

*This is your time. Walk on, smile, take a beat before you speak. Most people start talking before the room is actually listening.*

**Suggested opener:**

"Good morning. My name is Ananya Aithal, and I'm a Graduate Programme Associate in the ICS Audit team here at GBS Bangalore — which means on most days I do internal audit work, and on the rest of the days I quietly turn into a software developer and pretend I didn't.

Outside of Standard Chartered, I'm also a quantum machine learning researcher at ICTS-TIFR, which is the part of my life where I get to wear the 'physics nerd' hat. So today's topic — quantum cryptography — sits exactly at the intersection of my two jobs. Which is a polite way of saying: I have been waiting *months* to give this talk to a room full of auditors.

I have 35 minutes. I'm going to skip the last two slides on what Internal Audit specifically should do — my manager is covering that part — so I'll focus on the *why* and the *what.* My promise to you: by the end of this, even if you walked in thinking quantum computing is a sci-fi concept, you'll walk out understanding why this is on our risk register and why 2026 is not a year we want to sleep through.

Let's go."

*[Click to slide 1]*

---

## SLIDE 1 — What is Quantum Cryptography? *(~4 min)*

**[0:00 — Frame the slide]**

"Three columns. Three words. Let's break them down — because if I just say 'quantum cryptography' and assume everyone in the room knows what that means, half of you will spend the next 35 minutes nodding politely while secretly googling it under the table. Which is fair. I've done that in plenty of meetings."

**[0:30 — Quantum]**

"'Quantum' just means very, very small. The smallest particles in physics — photons, electrons, atoms. And at that scale, particles do things that our brains, which evolved to dodge tigers and catch fruit, were never built to understand.

Three properties matter for today.

*Superposition.* A particle can be in multiple states at once. Not 'we don't know which state' — it is genuinely in both until you check. The textbook example is Schrödinger's cat: alive and dead at the same time until someone opens the box. If anyone in this room has a cat, you already know they exist in a superposition of 'cute' and 'plotting your death.'

*Entanglement.* Two particles can be linked so that whatever happens to one instantly affects the other — across any distance. Einstein called this 'spooky action at a distance,' which is the most Einstein way of saying 'I hate this and I wish it would stop.' He was right that it's spooky. He was wrong that it doesn't happen — we've now demonstrated it across thousands of kilometers.

*The measurement effect.* Observing a quantum state changes it. This is the one that matters for cryptography. You cannot peek without leaving fingerprints."

**[2:30 — Cryptography]**

"Cryptography you all know. It's the science of turning readable data into nonsense, so that only authorized people can turn it back. Every time you log into mobile banking, type a password, or send a SWIFT message — cryptography is the thing keeping you out of a regulatory filing."

**[3:00 — The combination]**

"Put the two together. Quantum cryptography uses these strange physical properties to secure communication. The security doesn't rest on math — on a problem we *believe* is hard. It rests on physics — on a property of the universe itself.

Any attempt to intercept the message physically disturbs the quantum state, and the recipient sees it instantly. It's the difference between a complicated lock and a sealed envelope that visibly tears the moment anyone touches it."

**[3:45 — Transition]**

"Now, I just used the words 'physics' and 'universe.' If you're thinking 'this sounds expensive and far away,' the next slide is for you."

*[Click]*

---

## SLIDE 2 — This Is Not Science Fiction *(~2 min)*

*Stand to the side. Let the image speak. This is your breather slide.*

**[0:00 — Anchor the image]**

"This is a photograph. It's not a render, it's not concept art. This is an actual quantum computer — IBM Quantum System One.

The gold thing that looks like a chandelier? That's a dilution refrigerator. The qubits — the quantum bits doing the computing — sit at the bottom of it, cooled to about 15 millikelvin. To put that in perspective: outer space is roughly 2.7 *kelvin*. So the inside of this machine is *colder than space.* In Bangalore, where we struggle to keep server rooms below 22 degrees, this is a deeply unfair comparison.

**[1:00 — The point]**

"I'm showing you this because I want to be very clear about one thing. When we talk about quantum cryptography in the rest of this presentation, we are not talking about a future technology. We're talking about a technology that exists today, in real labs, in real data centers — at IBM, Google, IonQ, Rigetti, the Chinese Academy of Sciences. The only question on the table is *when* it gets large enough to break the cryptography we use right now."

**[1:45 — Transition]**

"Which brings us to a fair question: how is this any different from the cryptography we already use? Let's compare."

*[Click]*

---

## SLIDE 3 — Classical vs Quantum Cryptography *(~5 min)*

**[0:00 — Frame the slide]**

"This slide is the heart of the technical part of the talk. Long table, but it earns its space. Walk through it with me, row by row."

**[0:20 — Security basis]**

"*Security basis.* Classical cryptography rests on math problems we *believe* are hard. The word 'believe' is doing a lot of heavy lifting in that sentence. Factoring large numbers, discrete logarithms — we don't have a proof they're hard. We have a few decades of very smart people trying and failing.

Quantum cryptography rests on the laws of physics. There is no 'we believe.' Measurement disturbs state. That's not an assumption — it's a property of the universe, and it has been tested to a precision that would embarrass most other branches of science."

**[1:30 — Analogies]**

"*The analogy in the slide is the one I like best.* Classical crypto is a complicated puzzle box. With enough cleverness or enough computing power, you eventually solve it. Quantum crypto is a sealed envelope that tears the moment someone touches it.

*Can it be broken?* Classical: yes, with enough quantum computing power. Quantum: no — physically impossible.

*Can you tell if someone is eavesdropping?* Classical: no. Someone could be sitting on your wire right now and you'd never know. Quantum: yes, instantly. The protocol guarantees it.

*Future-proof?* Classical: no. Quantum: yes. At least until physics changes, which would be bad for many other reasons too."

**[3:00 — The compute comparison]**

"Now look at the bottom half. Classical computing uses bits — zero or one — processes them sequentially, scales linearly. Quantum computing uses qubits — zero AND one simultaneously through superposition — processes in parallel, scales exponentially.

The number that should make you sit up: RSA-2048, which is the encryption protecting most banking traffic today, including a great deal of ours. A classical computer would need *300 trillion years* to break it. The age of the universe is roughly 14 billion years. So we are very safe from classical computers.

A sufficiently large quantum computer? About 8 hours.

*Pause.*

300 trillion years. Eight hours. That is not a 10x speedup. That is a 'we need to migrate' speedup."

**[4:15 — Willow]**

"The image on the right is Google's Willow chip, announced late 2024. In a benchmark physics simulation, Willow showed a 13,000x speedup over the world's best classical supercomputer. Willow is not yet large enough to break RSA-2048. *Yet.* That word — 'yet' — is the entire reason I'm standing here today."

**[4:45 — Transition]**

"So if it's not here yet, why now? Why not wait? Why not let the Cybersecurity team handle it in 2032? Slide four."

*[Click]*

---

## SLIDE 4 — Why Do We Need It Now? Timeline *(~5 min)*

**[0:00 — Frame]**

"This is the slide I'd photograph if I were in your seat. The one to send to your manager when they ask why this is on the audit plan."

**[0:20 — The recent past]**

"*2022.* Santander Bank executes the first quantum-secured banking transaction. Spain to South America, QKD-protected. Real wire, real money. We'll come back to this.

*2023.* IBM unveils the Condor processor — 1,121 qubits. A 10x increase in just four years. NIST announces the winners of its post-quantum cryptography competition.

*2024 — current state.* NIST publishes the *final* post-quantum standards in August. China runs a quantum network spanning over 10,000 kilometers. Europe commits one billion euros to a quantum communication infrastructure. Nobody is asking 'should we' anymore. The conversation has moved entirely to 'when and how.'"

**[2:00 — The decision points]**

"*2025.* Regulatory mandates begin. The EU Cybersecurity Act gets amendments. Financial institutions are being *told* — not asked — to assess quantum vulnerability.

*2026 — circle this one in your notes.* This is the critical decision point. Roughly 5,000-qubit systems will be demonstrated. The 'harvest now, decrypt later' threat — which I'll explain in detail in two slides — gets serious. And here's the math that should keep us awake: data we encrypt in 2026 becomes vulnerable around 2036. That window — ten years — is squarely inside our retention period for mortgage records, KYC files, payment metadata, basically everything that makes us a bank.

This is the last comfortable migration window. After 2026, we are not in strategy mode. We are in remediation mode. Those have very different budgets, very different optics, and very different conversations with regulators."

**[3:30 — The harder horizon]**

"*2028 to 2029.* RSA-1024 broken reliably. RSA-2048 at risk from well-funded adversaries — read: nation-states with research budgets bigger than some countries.

*2030 to 2033.* The cryptographically relevant quantum computer. One million-plus qubits with error correction. RSA-2048 falls in hours. ECDSA falls in hours. All classical public-key cryptography becomes obsolete.

*2035 and beyond.* If we prepared, we are a secure industry leader. If we delayed — billions in losses, forced disclosures, regulatory fines, and a very awkward meeting with the Board."

**[4:30 — Transition]**

"Speaking of NIST publishing the final standards — let's pause on that for a second."

*[Click]*

---

## SLIDE 5 — August 2024: The Standards Are Final *(~2 min)*

*Breather slide. Stand still. Let it land.*

**[0:00 — Anchor]**

"This is the building where the rules of cryptographic engineering get written for the next decade. NIST — the US National Institute of Standards and Technology, headquartered in Gaithersburg, Maryland.

In August 2024, after eight years of public review, NIST published the *final* post-quantum cryptography standards. Three of them: ML-KEM, for key encapsulation. ML-DSA, for digital signatures. SLH-DSA, for hash-based signatures. The names sound like Tesla model numbers, but I promise these are the most reviewed cryptographic algorithms in human history."

**[1:00 — Why it matters]**

"Why does this matter for us? Because 'final' changes the regulatory conversation. Until 2024, you could tell a regulator, 'We're waiting for the standards to mature.' From August 2024 onward, that answer doesn't work. The standards are final. They are public. Vendors are implementing them. The SEC, the Federal Reserve, the EU — every regulator that touches financial services has started citing them in compliance guidance.

So when someone in a meeting says 'this is too early to act on,' the right reply is: the standards have a *finalized* version number. We're not early."

**[1:45 — Transition]**

"Now, the standards exist because of the threats. Let's get specific about what we're defending against."

*[Click]*

---

## SLIDE 6 — Types of Quantum Attacks *(~5 min)*

**[0:00 — Frame the asymmetry]**

"Five attacks on the slide. They are *not* equal. Four of them are future threats. One is happening right now, today, while we're sitting in this room. Let's start with the dangerous one."

**[0:30 — HNDL]**

"*Attack 1 — Harvest Now, Decrypt Later.* HNDL. The mechanic is almost insultingly simple. Adversary captures your encrypted traffic today. They store it. Five years, ten years, fifteen years. When quantum decryption matures, they unlock everything they've been hoarding.

This is not theoretical. State-sponsored adversaries are *already* recording encrypted bank traffic, government communications, corporate data — on the bet that they'll be able to read it in the 2030s. From their point of view, it's a cheap bet. Storage is essentially free. Patience is free. The only thing they need is a future quantum computer, and they're confident it's coming.

What gets harvested? Look at the list. Social Security numbers and dates of birth — identity markers that don't expire. You can't reissue your fingerprint. Strategic business decisions, M&A discussions, intellectual property. Anything where the value lasts a decade.

For Standard Chartered specifically: 15-year mortgage retention. KYC archives. Payment metadata. All of it harvest-able today. All of it readable in a decade if we don't migrate."

**[2:30 — The other attacks]**

"The other four shape what we audit *for* today, even if they aren't yet operational.

*Shor's algorithm.* Mid-1990s mathematics — Peter Shor at Bell Labs. He showed that a sufficiently large quantum computer can factor large numbers efficiently. That single insight retroactively makes RSA, ECDSA, and Diffie-Hellman vulnerable. Basically every public-key system we use. Timeline: 2030 to 2035.

*Grover's algorithm.* Does for symmetric crypto what Shor does for asymmetric. It effectively halves the security of AES. AES-128 becomes equivalent to AES-64 — broken. The fix is straightforward: move to AES-256. The hard part is finding every place we use AES-128 and swapping it. Hint: it's a lot of places.

*Quantum side-channel.* Future quantum sensors that can read the physical leakage from a chip — the heat, the electromagnetic emissions — and reconstruct keys. Doesn't break the math, breaks the implementation.

*Quantum man-in-the-middle.* Real-time decryption and impersonation during a live session. The 2030+ horror story."

**[4:30 — Transition]**

"Out of all of those, HNDL is the only one happening today. Which means it's the only one we can actually do something about today. Where does HNDL physically take place? Glad you asked."

*[Click]*

---

## SLIDE 7 — Where "Harvest Now" Actually Happens *(~2 min)*

*Breather. Let the image work.*

**[0:00 — Anchor]**

"This is what an adversary's data center probably looks like. Rows of racks, blinking lights, fiber. It looks like *our* data centers, because of course it does — they're built from the same parts.

The encrypted traffic being recorded right now sits in facilities that look exactly like this. Possibly more boring. Probably with worse lighting and free snacks."

**[0:45 — The point]**

"Here's the asymmetry I want you to take from this slide. Adversaries don't need to break the encryption today. They just need to *store* it. Storage is cheap. Patience is free. Even moderately competent intelligence agencies can afford to record the entire SWIFT network for a decade if they think the payoff is real.

And the payoff is very real. Imagine reading every payment instruction sent in 2024 — knowing every counterparty, every amount, every settlement. That's not fraud. That's *intelligence.* It rewrites the geopolitics of finance."

**[1:30 — Transition]**

"So if we don't migrate, what does that actually look like in practice? In a real customer interaction? Slide eight."

*[Click]*

---

## SLIDE 8 — What Happens If We Don't Act *(~4 min)*

**[0:00 — Frame]**

"Two scenarios. Both are real customer journeys at SCB. Both work the same on the surface. The difference is what's underneath."

**[0:20 — Scenario 1: Mobile banking]**

"*Scenario 1 — Customer logs into mobile banking.* Today: their phone establishes a TLS 1.2 connection to our server using RSA-2048. They type a password. They get in. Smooth, fast, normal.

The problem? RSA-2048 is exactly what falls to a quantum computer in eight hours.

In the quantum-safe future: same login, same speed, same UX. Underneath, the TLS handshake uses a post-quantum algorithm — Kyber, or its formal name ML-KEM. The customer notices nothing. Their phone is a few hundred milliseconds slower on the handshake, which is to say, nobody notices.

This is the nice part of the story. The fix is real, the standards exist, the customer experience is identical. We just have to do the work."

**[2:00 — Scenario 2: SWIFT]**

"*Scenario 2 — a $10 million wire from Branch A to Branch B over SWIFT.* Today: TLS 1.3 with RSA. Encrypted, sent, received. Looks fine.

But here's where HNDL turns into a horror story. An adversary records that encrypted message *today.* They store it. In 2034, they decrypt it with a quantum computer. Now they know every payment instruction we sent in 2024. Every counterparty, every amount, every routing. That data is gold for fraud, for blackmail, for competitive intelligence, for nation-state strategy. And it's gold *years* after the original transaction settled.

In the quantum-safe future: PQC plus QKD. The eavesdropping isn't just hard, it's *detectable.* If someone tried to record this wire, the protocol would tell us in real time."

**[3:15 — Santander]**

"This isn't theoretical. Santander did it in 2022. Spain to South America. First quantum-secured international wire. Zero successful interceptions. The protocol detected every probe attempt instantly. That's the case study on the next slide."

**[3:45 — Transition]**

"Let's talk about that wire."

*[Click]*

---

## SLIDE 9 — Santander, 2022: First Quantum-Secured Wire *(~2 min)*

*Breather. Use this for the case study moment.*

**[0:00 — Anchor]**

"Santander. Big Spanish bank. Operates in 10 markets globally. They have the same regulatory pressures we have, the same legacy systems we have, the same migration cost concerns. And in 2022, they ran the first quantum-secured international wire transfer between Spain and a partner in South America.

What does that mean concretely? They used QKD — quantum key distribution — to generate the encryption keys, with photons traveling over a fiber link. They encrypted a real transaction, real money. And they ran it production-style: monitored, logged, reconciled."

**[1:00 — The result]**

"Two outcomes worth knowing. First, zero successful interceptions. Second — and this is the one I love — the protocol detected every probe attempt *instantly.* Which means they not only protected the transaction, they got a real-time picture of who was trying to listen.

The reason this matters for us: it's a proof point. A peer institution, with broadly comparable complexity, did this three years ago. When the question is 'is this even possible at our scale,' the answer is: another bank's already done it. The question is whether *we* do it before regulators force us to."

**[1:45 — Transition]**

"So if we agree this needs to happen — who actually does it? Who in the building owns this work? Slide ten."

*[Click]*

---

## SLIDE 10 — Who Will Make This Happen? *(~4 min)*

**[0:00 — Frame]**

"Four internal teams, four external vendor categories. This is a coordination problem as much as a technical problem. Let me walk through it."

**[0:30 — Internal teams]**

"*Cybersecurity Team — the lead.* Overall strategy, governance, policy, risk assessment, vendor management, compliance. They own the *what* and the *when.*

*Network Infrastructure.* They deploy the quantum hardware. QKD devices between data centers, quantum channels, monitoring. This is the team that actually plugs things in.

*Application Security.* They implement post-quantum cryptography in our applications. Every app that uses TLS, every service that signs anything, every key in any library. This is the largest workload by far — hundreds of applications, dozens of crypto libraries, every legacy integration.

*Key Management.* They run the quantum key infrastructure itself. Key rotation, lifecycle, integration with HSMs, audit logging. Without them, the rest is theatre."

**[2:00 — External vendors]**

"On the right column, the external vendors.

*AWS Braket* — cloud-based quantum computing for testing and development.

*ID Quantique* — Swiss company, the QKD hardware specialists. Most production QKD links you've seen in the news run on their kit.

*PQShield* — UK firm focused entirely on post-quantum cryptography libraries. They're already in supply chains we depend on.

*QuintessenceLabs* — Australian, focused on quantum random number generation, which is the foundation of strong keys."

**[3:00 — The honest part]**

"None of these teams can do this alone. And — being honest — none of them have this on their top priority list right now, because everyone has a 2025 deliverable that feels more urgent. Which is exactly why governance matters. And which is exactly why Internal Audit has a role to play.

I'm going to hand over to my manager now to talk about what that role looks like for us specifically."

**[3:45 — Hand-off]**

"Thank you for staying with me through 35 minutes of physics, regulation, and bank infrastructure. I know that's not the lightest hour. Over to you."

*[Take a small bow, step aside, hand over.]*

---

## 💡 Quick Tips for Delivery

- **Don't read these notes verbatim.** Use them as the spine of the talk. Read them out loud twice while practicing — once for content, once for pacing — and then close the doc.
- **Time check at slide 4.** That's the timeline slide, your halfway point. If you're past 17 minutes here, speed up. If you're under 14 minutes, you can afford to slow down on the attack slide.
- **The breather slides (2, 5, 7, 9) are where you breathe and the audience absorbs.** Don't rush them. Stand still. Let the image carry the moment.
- **If a question lands mid-slide,** answer briefly and offer to take the rest at the end. You don't have buffer time for a long detour.
- **The "300 trillion years vs 8 hours" line on slide 3** — pause after it. That's your single best pull-quote of the talk.
- **If you forget a number,** say "the order of magnitude is what matters" and keep moving. Nobody is going to fact-check 5,000 qubits versus 4,800 qubits in real time.

Good luck. You've got this.
