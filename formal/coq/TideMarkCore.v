From Coq Require Import List Bool Arith PeanoNat Lia ZArith.
Import ListNotations.
Set Implicit Arguments.
Set Asymmetric Patterns.

(** TideMark proof-assistant core.

    This development verifies the structural composition layer of the paper.
    It is intentionally parameterized by two local interfaces:
      - a legal adjacent command pair commutes semantically; and
      - orienting one carrier establishes its bit and frames disjoint carriers.

    The paper supplies local arguments for the concrete prototype; bounded
    Python checks supplement them without constituting an SMT or kernel verdict.
    This file does not claim a refinement proof for either Python implementation. *)

Definition Id := nat.
Definition Pair := (Id * Id)%type.

Definition pair_valid (q : Pair) : Prop := fst q <> snd q.

Definition pair_disjoint (q r : Pair) : Prop :=
  fst q <> fst r /\
  fst q <> snd r /\
  snd q <> fst r /\
  snd q <> snd r.

Inductive NonOverlapping : list Pair -> Prop :=
| NO_nil : NonOverlapping []
| NO_cons : forall q qs,
    pair_valid q ->
    (forall r, In r qs -> pair_disjoint q r) ->
    NonOverlapping qs ->
    NonOverlapping (q :: qs).

Definition id_mem (x : Id) (xs : list Id) : bool :=
  existsb (Nat.eqb x) xs.

Definition eligible (q : Pair) (used : list Id) : bool :=
  negb (Nat.eqb (fst q) (snd q)) &&
  negb (id_mem (fst q) used) &&
  negb (id_mem (snd q) used).

Fixpoint greedy_aux (candidates : list Pair) (used : list Id) : list Pair :=
  match candidates with
  | [] => []
  | q :: rest =>
      if eligible q used
      then q :: greedy_aux rest (fst q :: snd q :: used)
      else greedy_aux rest used
  end.

Definition greedy_select (candidates : list Pair) : list Pair :=
  greedy_aux candidates [].

Lemma id_mem_false_not_in : forall x xs,
  id_mem x xs = false -> ~ In x xs.
Proof.
  intros x xs Hmem Hin.
  unfold id_mem in Hmem.
  induction xs as [|a xs IH]; simpl in *; [contradiction|].
  apply Bool.orb_false_iff in Hmem as [Hxa Hrest].
  destruct Hin as [<-|Hin].
  - apply Nat.eqb_neq in Hxa. contradiction.
  - apply IH; assumption.
Qed.

Lemma id_mem_true_in : forall x xs,
  id_mem x xs = true -> In x xs.
Proof.
  intros x xs Hmem.
  unfold id_mem in Hmem.
  apply existsb_exists in Hmem.
  destruct Hmem as [y [Hin Heq]].
  apply Nat.eqb_eq in Heq. subst. exact Hin.
Qed.

Lemma eligible_facts : forall q used,
  eligible q used = true ->
  fst q <> snd q /\ ~ In (fst q) used /\ ~ In (snd q) used.
Proof.
  intros [x y] used H.
  unfold eligible in H; simpl in H.
  repeat rewrite Bool.andb_true_iff in H.
  destruct H as [[Hxy Hx] Hy].
  apply Bool.negb_true_iff in Hxy.
  apply Bool.negb_true_iff in Hx.
  apply Bool.negb_true_iff in Hy.
  apply Nat.eqb_neq in Hxy.
  split; [exact Hxy|].
  split; [now apply id_mem_false_not_in|now apply id_mem_false_not_in].
Qed.

Lemma greedy_aux_avoids_used : forall candidates used q,
  In q (greedy_aux candidates used) ->
  ~ In (fst q) used /\ ~ In (snd q) used.
Proof.
  induction candidates as [|c rest IH]; intros used q Hin; simpl in Hin.
  - contradiction.
  - destruct (eligible c used) eqn:Helig.
    + simpl in Hin. destruct Hin as [<-|Hin].
      * destruct (eligible_facts _ _ Helig) as [_ [H1 H2]]. auto.
      * specialize (IH (fst c :: snd c :: used) q Hin) as [H1 H2].
        split; intro H;
          [apply H1 | apply H2]; simpl; auto.
    + now apply IH in Hin.
Qed.

Lemma greedy_aux_nonoverlap : forall candidates used,
  NonOverlapping (greedy_aux candidates used).
Proof.
  induction candidates as [|q rest IH]; intros used; simpl.
  - constructor.
  - destruct (eligible q used) eqn:Helig.
    + constructor.
      * destruct (eligible_facts _ _ Helig) as [Hvalid _]. exact Hvalid.
      * intros r Hin.
        pose proof (greedy_aux_avoids_used rest
          (fst q :: snd q :: used) r Hin) as [Hr1 Hr2].
        unfold pair_disjoint.
        repeat split; intro Heq.
        -- apply Hr1. simpl. left. exact Heq.
        -- apply Hr2. simpl. left. exact Heq.
        -- apply Hr1. simpl. right; left. exact Heq.
        -- apply Hr2. simpl. right; left. exact Heq.
      * apply IH.
    + apply IH.
Qed.

Theorem greedy_select_nonoverlap : forall candidates,
  NonOverlapping (greedy_select candidates).
Proof. intros; apply greedy_aux_nonoverlap. Qed.

Lemma in_firstn : forall (A : Type) (n : nat) (xs : list A) (x : A),
  In x (firstn n xs) -> In x xs.
Proof.
  intros A n. induction n as [|n IH]; intros xs x Hin; simpl in Hin.
  - contradiction.
  - destruct xs as [|a xs]; simpl in *; [contradiction|].
    destruct Hin as [<-|Hin]; [left; reflexivity|right; now apply IH].
Qed.

Lemma nonoverlap_firstn : forall n qs,
  NonOverlapping qs -> NonOverlapping (firstn n qs).
Proof.
  induction n as [|n IH]; intros qs Hno; simpl; [constructor|].
  destruct qs as [|q qs]; simpl; [constructor|].
  inversion Hno as [|? ? Hvalid Hdis Htail]; subst.
  constructor.
  - exact Hvalid.
  - intros r Hin. apply Hdis. apply in_firstn in Hin. exact Hin.
  - apply IH. exact Htail.
Qed.

Definition descriptor (candidates : list Pair) (payload_length : nat) : list Pair :=
  firstn payload_length (greedy_select candidates).

Theorem descriptor_nonoverlap : forall candidates k,
  NonOverlapping (descriptor candidates k).
Proof.
  intros. unfold descriptor. apply nonoverlap_firstn.
  apply greedy_select_nonoverlap.
Qed.

Definition Prefix {A : Type} (xs ys : list A) : Prop :=
  exists zs, ys = xs ++ zs.

Lemma firstn_prefix_monotone : forall (A : Type) (xs : list A) k l,
  k <= l -> Prefix (firstn k xs) (firstn l xs).
Proof.
  intros A xs k. generalize dependent xs.
  induction k as [|k IH]; intros xs l Hkl.
  - exists (firstn l xs). reflexivity.
  - destruct l as [|l]; [lia|].
    destruct xs as [|x xs].
    + exists []; reflexivity.
    + simpl. destruct (IH xs l) as [zs Hzs]; [lia|].
      exists zs. now rewrite Hzs.
Qed.

Theorem descriptor_prefix_monotone : forall candidates k l,
  k <= l -> Prefix (descriptor candidates k) (descriptor candidates l).
Proof.
  intros. unfold descriptor. now apply firstn_prefix_monotone.
Qed.

Theorem descriptor_value_independence : forall candidates (bits1 bits2 : list bool),
  length bits1 = length bits2 ->
  descriptor candidates (length bits1) = descriptor candidates (length bits2).
Proof. intros; now rewrite H. Qed.

Section CarrierComposition.
  Context {CarrierState : Type}.
  Variable orient : Pair -> bool -> CarrierState -> CarrierState.
  Variable decode : Pair -> CarrierState -> option bool.

  Hypothesis orient_establishes : forall q b s,
    decode q (orient q b s) = Some b.

  Hypothesis orient_frames_disjoint : forall q r b s,
    pair_disjoint q r ->
    decode r (orient q b s) = decode r s.

  Fixpoint orient_many (qs : list Pair) (bits : list bool)
      (s : CarrierState) : option CarrierState :=
    match qs, bits with
    | [], [] => Some s
    | q :: qs', b :: bits' =>
        match orient_many qs' bits' s with
        | Some s' => Some (orient q b s')
        | None => None
        end
    | _, _ => None
    end.

  Fixpoint extract_many (qs : list Pair) (s : CarrierState)
      : option (list bool) :=
    match qs with
    | [] => Some []
    | q :: qs' =>
        match decode q s, extract_many qs' s with
        | Some b, Some bits => Some (b :: bits)
        | _, _ => None
        end
    end.

  Lemma extract_many_frame : forall q qs b s,
    (forall r, In r qs -> pair_disjoint q r) ->
    extract_many qs (orient q b s) = extract_many qs s.
  Proof.
    intros q qs. induction qs as [|r rs IH]; intros b s Hdis; simpl.
    - reflexivity.
    - rewrite orient_frames_disjoint by (apply Hdis; simpl; auto).
      rewrite IH.
      + reflexivity.
      + intros r' Hin. apply Hdis. simpl; auto.
  Qed.

  Theorem exact_extraction_after_orient_many : forall qs bits s target,
    NonOverlapping qs ->
    orient_many qs bits s = Some target ->
    extract_many qs target = Some bits.
  Proof.
    intros qs bits. revert qs.
    induction bits as [|b bits IH]; intros qs s target Hno Horient.
    - destruct qs as [|q qs]; simpl in Horient; [inversion Horient; reflexivity|discriminate].
    - destruct qs as [|q qs]; simpl in Horient; [discriminate|].
      inversion Hno as [|? ? Hvalid Hdis Htail]; subst.
      destruct (orient_many qs bits s) as [mid|] eqn:Hmid; try discriminate.
      inversion Horient; subst target; clear Horient.
      simpl. rewrite orient_establishes.
      rewrite extract_many_frame by exact Hdis.
      rewrite (IH qs s mid Htail Hmid).
      reflexivity.
  Qed.
End CarrierComposition.

Section StructuralSemantics.
  Context {Value State Atom Cmd : Type}.

  Definition Env := Id -> Value.

  Variable atom_value : Atom -> Env -> Value.
  Variable atom_guard : Atom -> Env -> bool.
  Variable run_cmd : Cmd -> Env -> State -> (Value * State).

  Definition bind (rho : Env) (x : Id) (v : Value) : Env :=
    fun y => if Nat.eqb y x then v else rho y.

  Definition exec_bind (x : Id) (c : Cmd) (rho : Env) (st : State)
      : Env * State :=
    let '(v, st') := run_cmd c rho st in
    (bind rho x v, st').

  Definition exec_two (x : Id) (cx : Cmd) (y : Id) (cy : Cmd)
      (rho : Env) (st : State) : Env * State :=
    let '(rho1, st1) := exec_bind x cx rho st in
    exec_bind y cy rho1 st1.

  Inductive Expr : Type :=
  | ERet : Atom -> Expr
  | ELet : Id -> Cmd -> Expr -> Expr
  | EIf : Atom -> Expr -> Expr -> Expr.

  Fixpoint eval (e : Expr) (rho : Env) (st : State) : Value * State :=
    match e with
    | ERet a => (atom_value a rho, st)
    | ELet x c body =>
        let '(rho', st') := exec_bind x c rho st in
        eval body rho' st'
    | EIf a yes no =>
        if atom_guard a rho then eval yes rho st else eval no rho st
    end.

  (** Contextual commutation is the exact local semantic interface needed by
      structural replay.  It deliberately avoids requiring byte-for-byte equality
      of intermediate environments. *)
  Definition CommandsCommute (x : Id) (cx : Cmd) (y : Id) (cy : Cmd) : Prop :=
    forall tail rho st,
      eval (ELet x cx (ELet y cy tail)) rho st =
      eval (ELet y cy (ELet x cx tail)) rho st.

  Lemma eval_two_lets : forall x cx y cy tail rho st,
    eval (ELet x cx (ELet y cy tail)) rho st =
    let '(rho', st') := exec_two x cx y cy rho st in eval tail rho' st'.
  Proof.
    intros. simpl.
    destruct (exec_bind x cx rho st) as [rho1 st1] eqn:H1.
    simpl. unfold exec_two. now rewrite H1.
  Qed.

  Variable Legal : Id -> Cmd -> Id -> Cmd -> Prop.
  Hypothesis legal_commutes : forall x cx y cy,
    Legal x cx y cy -> CommandsCommute x cx y cy.

  Inductive StructuralDerivation : Expr -> Expr -> Prop :=
  | SD_ret : forall a,
      StructuralDerivation (ERet a) (ERet a)
  | SD_let : forall x c source_body target_body,
      StructuralDerivation source_body target_body ->
      StructuralDerivation (ELet x c source_body) (ELet x c target_body)
  | SD_if : forall a source_yes target_yes source_no target_no,
      StructuralDerivation source_yes target_yes ->
      StructuralDerivation source_no target_no ->
      StructuralDerivation (EIf a source_yes source_no)
                           (EIf a target_yes target_no)
  | SD_pair_identity : forall x cx y cy source_tail target_tail,
      Legal x cx y cy ->
      StructuralDerivation source_tail target_tail ->
      StructuralDerivation
        (ELet x cx (ELet y cy source_tail))
        (ELet x cx (ELet y cy target_tail))
  | SD_pair_swap : forall x cx y cy source_tail target_tail,
      Legal x cx y cy ->
      StructuralDerivation source_tail target_tail ->
      StructuralDerivation
        (ELet x cx (ELet y cy source_tail))
        (ELet y cy (ELet x cx target_tail)).

  Theorem structural_derivation_sound : forall source target,
    StructuralDerivation source target ->
    forall rho st, eval source rho st = eval target rho st.
  Proof.
    intros source target Hderiv.
    induction Hderiv; intros rho st.
    - reflexivity.
    - simpl. destruct (exec_bind x c rho st) as [rho' st'].
      now apply IHHderiv.
    - simpl. destruct (atom_guard a rho); auto.
    - repeat rewrite eval_two_lets.
      destruct (exec_two x cx y cy rho st) as [rho' st'].
      now apply IHHderiv.
    - transitivity (eval (ELet x cx (ELet y cy target_tail)) rho st).
      + repeat rewrite eval_two_lets.
        destruct (exec_two x cx y cy rho st) as [rho' st'].
        now apply IHHderiv.
      + now apply (legal_commutes H).
  Qed.

  Inductive FiniteReplay : Expr -> Expr -> Prop :=
  | FR_refl : forall e, FiniteReplay e e
  | FR_step : forall e1 e2 e3,
      StructuralDerivation e1 e2 ->
      FiniteReplay e2 e3 ->
      FiniteReplay e1 e3.

  Theorem finite_replay_sound : forall source target,
    FiniteReplay source target ->
    forall rho st, eval source rho st = eval target rho st.
  Proof.
    intros source target Hreplay.
    induction Hreplay; intros rho st.
    - reflexivity.
    - rewrite (structural_derivation_sound H rho st).
      apply IHHreplay.
  Qed.

  Variable candidates : Expr -> list Pair.
  Variable orient_expr : Pair -> bool -> Expr -> Expr.
  Variable decode_expr : Pair -> Expr -> option bool.

  Hypothesis orient_expr_establishes : forall q b e,
    decode_expr q (orient_expr q b e) = Some b.
  Hypothesis orient_expr_frames : forall q r b e,
    pair_disjoint q r ->
    decode_expr r (orient_expr q b e) = decode_expr r e.

  Definition canonical_descriptor (source : Expr) (bits : list bool) : list Pair :=
    descriptor (candidates source) (length bits).

  Record CoreAccepted (source target : Expr) (bits : list bool)
      (desc : list Pair) : Prop := {
    accepted_canonical : desc = canonical_descriptor source bits;
    accepted_replay : FiniteReplay source target;
    accepted_target : orient_many orient_expr desc bits source = Some target
  }.

  Theorem core_checker_sound : forall source target bits desc,
    CoreAccepted source target bits desc ->
    (forall rho st, eval source rho st = eval target rho st) /\
    desc = canonical_descriptor source bits /\
    NonOverlapping desc /\
    extract_many decode_expr desc target = Some bits.
  Proof.
    intros source target bits desc Hacc.
    destruct Hacc as [Hcanon Hreplay Htarget].
    split.
    - now apply finite_replay_sound.
    - split; [exact Hcanon|].
      split.
      + rewrite Hcanon. unfold canonical_descriptor.
        apply descriptor_nonoverlap.
      + eapply (@exact_extraction_after_orient_many Expr orient_expr decode_expr
                    orient_expr_establishes orient_expr_frames
                    desc bits source target).
        * rewrite Hcanon. unfold canonical_descriptor.
          apply descriptor_nonoverlap.
        * exact Htarget.
  Qed.

  Definition ExtractorChecked (target : Expr) (bits : list bool)
      (desc : list Pair) : Prop :=
    extract_many decode_expr desc target = Some bits.

  Theorem checked_acceptance_has_no_semantic_extraction_circularity :
    forall source target bits desc,
      CoreAccepted source target bits desc ->
      ExtractorChecked target bits desc ->
      (forall rho st, eval source rho st = eval target rho st) /\
      ExtractorChecked target bits desc.
  Proof.
    intros source target bits desc Hcore Hcheck.
    split.
    - destruct (core_checker_sound Hcore) as [Hsem _]. exact Hsem.
    - exact Hcheck.
  Qed.

  Theorem accepted_descriptor_value_independent : forall source bits1 bits2,
    length bits1 = length bits2 ->
    canonical_descriptor source bits1 = canonical_descriptor source bits2.
  Proof.
    intros. unfold canonical_descriptor.
    now apply descriptor_value_independence.
  Qed.
End StructuralSemantics.

(** Exported theorem inventory. *)
Check greedy_select_nonoverlap.
Check descriptor_nonoverlap.
Check descriptor_prefix_monotone.
Check descriptor_value_independence.
Check exact_extraction_after_orient_many.
Check structural_derivation_sound.
Check finite_replay_sound.
Check core_checker_sound.
Check checked_acceptance_has_no_semantic_extraction_circularity.
Check accepted_descriptor_value_independent.
Print Assumptions greedy_select_nonoverlap.
Print Assumptions exact_extraction_after_orient_many.
Print Assumptions structural_derivation_sound.
Print Assumptions core_checker_sound.

Module ConcreteWitness.
  Definition WValue := nat.
  Definition WState := nat.
  Definition WAtom := nat.
  Definition WCmd := nat.
  Definition WEnv := @Env WValue.

  Definition w_atom_value (a : WAtom) (_ : WEnv) : WValue := a.
  Definition w_atom_guard (a : WAtom) (_ : WEnv) : bool := Nat.even a.
  Definition w_run_cmd (c : WCmd) (_ : WEnv) (st : WState)
      : WValue * WState := (c, st).
  Definition w_legal (x : Id) (_ : WCmd) (y : Id) (_ : WCmd) : Prop := x <> y.

  Lemma w_eval_env_irrelevant : forall (e : @Expr WAtom WCmd) rho1 rho2 st,
    @eval WValue WState WAtom WCmd w_atom_value w_atom_guard w_run_cmd
      e rho1 st =
    @eval WValue WState WAtom WCmd w_atom_value w_atom_guard w_run_cmd
      e rho2 st.
  Proof.
    induction e; intros rho1 rho2 st; simpl.
    - reflexivity.
    - apply IHe.
    - unfold w_atom_guard. destruct (Nat.even a); [apply IHe1 | apply IHe2].
  Qed.

  Lemma w_legal_commutes : forall x cx y cy,
    w_legal x cx y cy -> @CommandsCommute WValue WState WAtom WCmd
      w_atom_value w_atom_guard w_run_cmd x cx y cy.
  Proof.
    intros x cx y cy _ tail rho st.
    simpl. apply w_eval_env_irrelevant.
  Qed.

  Definition w_source : @Expr WAtom WCmd :=
    ELet 1 10 (ELet 2 20 (ERet 0)).
  Definition w_target : @Expr WAtom WCmd :=
    ELet 2 20 (ELet 1 10 (ERet 0)).

  Lemma w_derivation : @StructuralDerivation WAtom WCmd w_legal w_source w_target.
  Proof.
    unfold w_source, w_target.
    apply SD_pair_swap.
    - unfold w_legal. discriminate.
    - constructor.
  Qed.

  Theorem w_observation_preserved : forall rho st,
    @eval WValue WState WAtom WCmd w_atom_value w_atom_guard w_run_cmd
      w_source rho st =
    @eval WValue WState WAtom WCmd w_atom_value w_atom_guard w_run_cmd
      w_target rho st.
  Proof.
    intros.
    eapply (@structural_derivation_sound WValue WState WAtom WCmd
              w_atom_value w_atom_guard w_run_cmd w_legal
              w_legal_commutes w_source w_target w_derivation).
  Qed.

  Definition pair_eq_dec : forall (q r : Pair), {q = r} + {q <> r}.
  Proof. decide equality; apply Nat.eq_dec. Defined.

  Definition CState := Pair -> option bool.
  Definition cdecode (q : Pair) (s : CState) : option bool := s q.
  Definition corient (q : Pair) (b : bool) (s : CState) : CState :=
    fun r => if pair_eq_dec r q then Some b else s r.

  Lemma corient_establishes : forall q b s,
    cdecode q (corient q b s) = Some b.
  Proof.
    intros. unfold cdecode, corient.
    destruct (pair_eq_dec q q); [reflexivity|contradiction].
  Qed.

  Lemma pair_disjoint_neq : forall q r,
    pair_disjoint q r -> r <> q.
  Proof.
    intros q r Hdis Heq. subst r.
    destruct Hdis as [Hcontra _]. apply Hcontra. reflexivity.
  Qed.

  Lemma corient_frames : forall q r b s,
    pair_disjoint q r ->
    cdecode r (corient q b s) = cdecode r s.
  Proof.
    intros. unfold cdecode, corient.
    destruct (pair_eq_dec r q); [exfalso; now apply (pair_disjoint_neq H) | reflexivity].
  Qed.

  Definition q1 : Pair := (1, 2).
  Definition q2 : Pair := (3, 4).
  Definition witness_desc : list Pair := [q1; q2].
  Definition witness_bits : list bool := [true; false].
  Definition empty_carriers : CState := fun _ => None.
  Definition witness_target : CState :=
    corient q1 true (corient q2 false empty_carriers).

  Lemma q1_q2_disjoint : pair_disjoint q1 q2.
  Proof. unfold pair_disjoint, q1, q2; simpl; repeat split; discriminate. Qed.

  Lemma witness_nonoverlap : NonOverlapping witness_desc.
  Proof.
    unfold witness_desc.
    constructor.
    - unfold pair_valid, q1; simpl; discriminate.
    - intros r Hin. simpl in Hin. destruct Hin as [<-|Hin].
      + exact q1_q2_disjoint.
      + contradiction.
    - constructor.
      + unfold pair_valid, q2; simpl; discriminate.
      + intros r Hin. contradiction.
      + constructor.
  Qed.

  Lemma witness_orientation_run :
    orient_many corient witness_desc witness_bits empty_carriers = Some witness_target.
  Proof. reflexivity. Qed.

  Theorem witness_exact_extraction :
    extract_many cdecode witness_desc witness_target = Some witness_bits.
  Proof.
    eapply (@exact_extraction_after_orient_many CState corient cdecode
              corient_establishes corient_frames
              witness_desc witness_bits empty_carriers witness_target).
    - exact witness_nonoverlap.
    - exact witness_orientation_run.
  Qed.

  Example witness_selector_skips_overlap :
    greedy_select [q1; (2, 3); q2] = [q1; q2].
  Proof. reflexivity. Qed.
End ConcreteWitness.

Check ConcreteWitness.w_observation_preserved.
Check ConcreteWitness.witness_exact_extraction.
Check ConcreteWitness.witness_selector_skips_overlap.
Print Assumptions ConcreteWitness.w_observation_preserved.
Print Assumptions ConcreteWitness.witness_exact_extraction.



(** Concrete command-level effect adequacy for an atom-valued command subset.
    This is not the production parser/type checker: it also admits CAUnit,
    equality of unit values and emitting unit. No full-grammar refinement is
    claimed from this reusable model. *)
Module ConcreteEffectAdequacy.

  Inductive CType : Type :=
  | CTInt
  | CTBool
  | CTUnit.

  Definition ctype_eqb (t u : CType) : bool :=
    match t, u with
    | CTInt, CTInt | CTBool, CTBool | CTUnit, CTUnit => true
    | _, _ => false
    end.

  Lemma ctype_eqb_eq : forall t u,
    ctype_eqb t u = true -> t = u.
  Proof. destruct t, u; simpl; intros; try discriminate; reflexivity. Qed.

  Inductive CValue : Type :=
  | CVInt : Z -> CValue
  | CVBool : bool -> CValue
  | CVUnit.

  Inductive CAtom : Type :=
  | CAVar : Id -> CAtom
  | CAInt : Z -> CAtom
  | CABool : bool -> CAtom
  | CAUnit.

  Inductive CPure : Type :=
  | CPCopy : CAtom -> CPure
  | CPAdd : CAtom -> CAtom -> CPure
  | CPSub : CAtom -> CAtom -> CPure
  | CPMul : CAtom -> CAtom -> CPure
  | CPEq : CAtom -> CAtom -> CPure
  | CPLt : CAtom -> CAtom -> CPure
  | CPNot : CAtom -> CPure.

  Inductive CCmd : Type :=
  | CCPure : CPure -> CCmd
  | CCGet : nat -> CCmd
  | CCPut : nat -> CAtom -> CCmd
  | CCEmit : CAtom -> CCmd.

  Inductive Resource : Type :=
  | RRegion : nat -> Resource
  | RTrace : Resource.

  Definition resource_eqb (r s : Resource) : bool :=
    match r, s with
    | RRegion x, RRegion y => Nat.eqb x y
    | RTrace, RTrace => true
    | _, _ => false
    end.

  Definition resource_mem (r : Resource) (xs : list Resource) : bool :=
    existsb (resource_eqb r) xs.

  Definition resources_intersect (xs ys : list Resource) : bool :=
    existsb (fun r => resource_mem r ys) xs.

  Record CEffect : Type := {
    ce_reads : list Resource;
    ce_writes : list Resource
  }.

  Definition command_effect (c : CCmd) : CEffect :=
    match c with
    | CCPure _ => {| ce_reads := []; ce_writes := [] |}
    | CCGet r => {| ce_reads := [RRegion r]; ce_writes := [] |}
    | CCPut r _ => {| ce_reads := []; ce_writes := [RRegion r] |}
    | CCEmit _ => {| ce_reads := []; ce_writes := [RTrace] |}
    end.

  Definition effects_conflict (e f : CEffect) : bool :=
    resources_intersect (ce_writes e) (ce_reads f ++ ce_writes f) ||
    resources_intersect (ce_writes f) (ce_reads e ++ ce_writes e).

  Definition commands_conflict (c d : CCmd) : bool :=
    effects_conflict (command_effect c) (command_effect d).

  Definition CEnv := @Env CValue.

  Definition atom_value (a : CAtom) (rho : CEnv) : CValue :=
    match a with
    | CAVar x => rho x
    | CAInt z => CVInt z
    | CABool b => CVBool b
    | CAUnit => CVUnit
    end.

  Definition value_eqb (v w : CValue) : bool :=
    match v, w with
    | CVInt z, CVInt z' => Z.eqb z z'
    | CVBool b, CVBool b' => Bool.eqb b b'
    | CVUnit, CVUnit => true
    | _, _ => false
    end.

  Definition int_binary (op : Z -> Z -> Z) (a b : CValue) : CValue :=
    match a, b with
    | CVInt x, CVInt y => CVInt (op x y)
    | _, _ => CVUnit
    end.

  Definition pure_value (p : CPure) (rho : CEnv) : CValue :=
    match p with
    | CPCopy a => atom_value a rho
    | CPAdd a b => int_binary Z.add (atom_value a rho) (atom_value b rho)
    | CPSub a b => int_binary Z.sub (atom_value a rho) (atom_value b rho)
    | CPMul a b => int_binary Z.mul (atom_value a rho) (atom_value b rho)
    | CPEq a b => CVBool (value_eqb (atom_value a rho) (atom_value b rho))
    | CPLt a b =>
        match atom_value a rho, atom_value b rho with
        | CVInt x, CVInt y => CVBool (Z.ltb x y)
        | _, _ => CVUnit
        end
    | CPNot a =>
        match atom_value a rho with
        | CVBool b => CVBool (negb b)
        | _ => CVUnit
        end
    end.

  Definition concrete_atom_guard (a : CAtom) (rho : CEnv) : bool :=
    match atom_value a rho with
    | CVBool b => b
    | _ => false
    end.

  Record CState : Type := {
    cs_regions : list CValue;
    cs_trace : list CValue
  }.

  Definition store_get (r : nat) (store : list CValue) : CValue :=
    nth r store CVUnit.

  Fixpoint store_put (r : nat) (v : CValue) (store : list CValue)
      : list CValue :=
    match r, store with
    | O, _ :: rest => v :: rest
    | S r', head :: rest => head :: store_put r' v rest
    | _, [] => []
    end.

  Lemma store_get_put_other : forall store r s v,
    r <> s -> store_get r (store_put s v store) = store_get r store.
  Proof.
    induction store as [|head rest IH]; intros r s v Hneq.
    - destruct r, s; reflexivity.
    - destruct r, s; simpl in *.
      + contradiction.
      + reflexivity.
      + reflexivity.
      + apply IH. congruence.
  Qed.

  Lemma store_put_commute : forall store r s v w,
    r <> s ->
    store_put r v (store_put s w store) =
    store_put s w (store_put r v store).
  Proof.
    induction store as [|head rest IH]; intros r s v w Hneq.
    - destruct r, s; reflexivity.
    - destruct r, s; simpl in *.
      + contradiction.
      + reflexivity.
      + reflexivity.
      + f_equal. apply IH. congruence.
  Qed.

  Definition run_cmd (c : CCmd) (rho : CEnv) (st : CState)
      : CValue * CState :=
    match c with
    | CCPure p => (pure_value p rho, st)
    | CCGet r => (store_get r (cs_regions st), st)
    | CCPut r a =>
        (CVUnit,
         {| cs_regions := store_put r (atom_value a rho) (cs_regions st);
            cs_trace := cs_trace st |})
    | CCEmit a =>
        (CVUnit,
         {| cs_regions := cs_regions st;
            cs_trace := cs_trace st ++ [atom_value a rho] |})
    end.

  Definition atom_mentions (x : Id) (a : CAtom) : bool :=
    match a with
    | CAVar y => Nat.eqb y x
    | _ => false
    end.

  Definition pure_mentions (x : Id) (p : CPure) : bool :=
    match p with
    | CPCopy a | CPNot a => atom_mentions x a
    | CPAdd a b | CPSub a b | CPMul a b | CPEq a b | CPLt a b =>
        atom_mentions x a || atom_mentions x b
    end.

  Definition command_mentions (x : Id) (c : CCmd) : bool :=
    match c with
    | CCPure p => pure_mentions x p
    | CCGet _ => false
    | CCPut _ a | CCEmit a => atom_mentions x a
    end.

  Lemma atom_value_bind_irrelevant : forall a x v rho,
    atom_mentions x a = false ->
    atom_value a (bind rho x v) = atom_value a rho.
  Proof.
    destruct a; intros; simpl in *; try reflexivity.
    unfold bind. now rewrite H.
  Qed.

  Lemma pure_value_bind_irrelevant : forall p x v rho,
    pure_mentions x p = false ->
    pure_value p (bind rho x v) = pure_value p rho.
  Proof.
    destruct p; intros; simpl in *.
    - now rewrite atom_value_bind_irrelevant by exact H.
    - apply Bool.orb_false_iff in H as [H1 H2].
      rewrite atom_value_bind_irrelevant by exact H1.
      now rewrite atom_value_bind_irrelevant by exact H2.
    - apply Bool.orb_false_iff in H as [H1 H2].
      rewrite atom_value_bind_irrelevant by exact H1.
      now rewrite atom_value_bind_irrelevant by exact H2.
    - apply Bool.orb_false_iff in H as [H1 H2].
      rewrite atom_value_bind_irrelevant by exact H1.
      now rewrite atom_value_bind_irrelevant by exact H2.
    - apply Bool.orb_false_iff in H as [H1 H2].
      rewrite atom_value_bind_irrelevant by exact H1.
      now rewrite atom_value_bind_irrelevant by exact H2.
    - apply Bool.orb_false_iff in H as [H1 H2].
      rewrite atom_value_bind_irrelevant by exact H1.
      now rewrite atom_value_bind_irrelevant by exact H2.
    - now rewrite atom_value_bind_irrelevant by exact H.
  Qed.

  Lemma run_cmd_bind_irrelevant : forall c x v rho st,
    command_mentions x c = false ->
    run_cmd c (bind rho x v) st = run_cmd c rho st.
  Proof.
    destruct c; intros; simpl in *.
    - now rewrite pure_value_bind_irrelevant by exact H.
    - reflexivity.
    - now rewrite atom_value_bind_irrelevant by exact H.
    - now rewrite atom_value_bind_irrelevant by exact H.
  Qed.

  Lemma atom_value_ext : forall a rho sigma,
    (forall x, rho x = sigma x) ->
    atom_value a rho = atom_value a sigma.
  Proof. destruct a; intros; simpl; try reflexivity. apply H. Qed.

  Lemma pure_value_ext : forall p rho sigma,
    (forall x, rho x = sigma x) ->
    pure_value p rho = pure_value p sigma.
  Proof.
    intros p rho sigma Hext. destruct p; simpl;
      repeat match goal with
      | |- context [atom_value ?a rho] =>
          rewrite (atom_value_ext a rho sigma Hext)
      end; reflexivity.
  Qed.

  Lemma run_cmd_env_ext : forall c rho sigma st,
    (forall x, rho x = sigma x) ->
    run_cmd c rho st = run_cmd c sigma st.
  Proof.
    intros c rho sigma st Hext. destruct c as [p|r|r a|a]; simpl.
    - rewrite (pure_value_ext p rho sigma Hext). reflexivity.
    - reflexivity.
    - rewrite (atom_value_ext a rho sigma Hext). reflexivity.
    - rewrite (atom_value_ext a rho sigma Hext). reflexivity.
  Qed.

  Lemma concrete_atom_guard_ext : forall a rho sigma,
    (forall x, rho x = sigma x) ->
    concrete_atom_guard a rho = concrete_atom_guard a sigma.
  Proof.
    intros. unfold concrete_atom_guard.
    rewrite (atom_value_ext a rho sigma H). reflexivity.
  Qed.

  Lemma concrete_eval_env_ext : forall (e : @Expr CAtom CCmd) rho sigma st,
    (forall x, rho x = sigma x) ->
    @eval CValue CState CAtom CCmd atom_value concrete_atom_guard run_cmd
      e rho st =
    @eval CValue CState CAtom CCmd atom_value concrete_atom_guard run_cmd
      e sigma st.
  Proof.
    induction e; intros rho sigma st Hext.
    - cbn [eval]. rewrite (atom_value_ext a rho sigma Hext). reflexivity.
    - cbn [eval exec_bind].
      pose proof (run_cmd_env_ext c rho sigma st Hext) as Hrun.
      destruct (run_cmd c rho st) as [v1 st1] eqn:Hleft.
      destruct (run_cmd c sigma st) as [v2 st2] eqn:Hright.
      inversion Hrun; subst v2 st2.
      unfold exec_bind. rewrite Hleft, Hright. simpl.
      apply IHe. intros z. unfold bind.
      destruct (Nat.eqb z i); [reflexivity | exact (Hext z)].
    - cbn [eval].
      rewrite (concrete_atom_guard_ext a rho sigma Hext).
      destruct (concrete_atom_guard a sigma); [apply IHe1 | apply IHe2]; exact Hext.
  Qed.

  Definition run_pair (c d : CCmd) (rho : CEnv) (st : CState)
      : CValue * CValue * CState :=
    let '(v, st1) := run_cmd c rho st in
    let '(w, st2) := run_cmd d rho st1 in
    (v, w, st2).

  Definition run_pair_reverse (c d : CCmd) (rho : CEnv) (st : CState)
      : CValue * CValue * CState :=
    let '(w, st1) := run_cmd d rho st in
    let '(v, st2) := run_cmd c rho st1 in
    (v, w, st2).

  Lemma conflict_get_put_formula : forall r s a,
    commands_conflict (CCGet r) (CCPut s a) = Nat.eqb s r.
  Proof.
    intros. unfold commands_conflict, effects_conflict, command_effect,
      resources_intersect, resource_mem, resource_eqb.
    simpl. destruct (Nat.eqb s r); reflexivity.
  Qed.

  Lemma conflict_put_get_formula : forall r s a,
    commands_conflict (CCPut r a) (CCGet s) = Nat.eqb r s.
  Proof.
    intros. unfold commands_conflict, effects_conflict, command_effect,
      resources_intersect, resource_mem, resource_eqb.
    simpl. destruct (Nat.eqb r s); reflexivity.
  Qed.

  Lemma conflict_put_put_formula : forall r s a b,
    commands_conflict (CCPut r a) (CCPut s b) =
    (Nat.eqb r s || Nat.eqb s r).
  Proof.
    intros. unfold commands_conflict, effects_conflict, command_effect,
      resources_intersect, resource_mem, resource_eqb.
    simpl. destruct (Nat.eqb r s), (Nat.eqb s r); reflexivity.
  Qed.

  Theorem run_pair_commutes_same_env : forall c d rho st,
    commands_conflict c d = false ->
    run_pair c d rho st = run_pair_reverse c d rho st.
  Proof.
    intros c d rho [store trace] Hconf.
    destruct c as [p|r|r a|a]; destruct d as [q|s|s b|b];
      cbn [run_pair run_pair_reverse run_cmd] in *;
      try reflexivity; try discriminate.
    - rewrite conflict_get_put_formula in Hconf.
      apply Nat.eqb_neq in Hconf.
      pose proof (@store_get_put_other store r s (atom_value b rho)
        (fun Heq => Hconf (eq_sym Heq))) as Hget.
      simpl. unfold store_get in *. rewrite Hget. reflexivity.
    - rewrite conflict_put_get_formula in Hconf.
      apply Nat.eqb_neq in Hconf.
      pose proof (@store_get_put_other store s r (atom_value a rho)
        (fun Heq => Hconf (eq_sym Heq))) as Hget.
      simpl. unfold store_get in *. rewrite Hget. reflexivity.
    - rewrite conflict_put_put_formula in Hconf.
      apply Bool.orb_false_iff in Hconf as [Hrs _].
      apply Nat.eqb_neq in Hrs.
      simpl.
      replace (store_put s (atom_value b rho)
                 (store_put r (atom_value a rho) store))
        with (store_put r (atom_value a rho)
                (store_put s (atom_value b rho) store)).
      + reflexivity.
      + apply store_put_commute. exact Hrs.
  Qed.

  Lemma bind_distinct_commute : forall (rho : CEnv) x y (vx vy : CValue),
    x <> y ->
    forall z,
      bind (bind rho x vx) y vy z = bind (bind rho y vy) x vx z.
  Proof.
    intros rho x y vx vy Hxy z. unfold bind.
    destruct (Nat.eqb z y) eqn:Hzy;
    destruct (Nat.eqb z x) eqn:Hzx; try reflexivity.
    apply Nat.eqb_eq in Hzy. apply Nat.eqb_eq in Hzx.
    subst. contradiction.
  Qed.

  Lemma exec_two_independent : forall x c y d rho st,
    command_mentions x d = false ->
    command_mentions y c = false ->
    commands_conflict c d = false ->
    exists vx vy final,
      @exec_two CValue CState CCmd run_cmd x c y d rho st =
        (bind (bind rho x vx) y vy, final) /\
      @exec_two CValue CState CCmd run_cmd y d x c rho st =
        (bind (bind rho y vy) x vx, final).
  Proof.
    intros x c y d rho st Hxd Hyc Hconf.
    pose proof (run_pair_commutes_same_env c d rho st Hconf) as Hpair.
    unfold run_pair, run_pair_reverse in Hpair.
    destruct (run_cmd c rho st) as [vx stx] eqn:Hc.
    destruct (run_cmd d rho stx) as [vy final] eqn:Hd_after.
    destruct (run_cmd d rho st) as [vy' sty] eqn:Hd.
    destruct (run_cmd c rho sty) as [vx' final'] eqn:Hc_after.
    cbn in Hpair.
    inversion Hpair; subst vy' vx' final'.
    exists vx, vy, final. split.
    - unfold exec_two, exec_bind. rewrite Hc. simpl.
      rewrite (run_cmd_bind_irrelevant d x vx rho stx Hxd).
      now rewrite Hd_after.
    - unfold exec_two, exec_bind. rewrite Hd. simpl.
      rewrite (run_cmd_bind_irrelevant c y vy rho sty Hyc).
      now rewrite Hc_after.
  Qed.

  Theorem independent_commands_commute : forall x c y d,
    x <> y ->
    command_mentions x d = false ->
    command_mentions y c = false ->
    commands_conflict c d = false ->
    @CommandsCommute CValue CState CAtom CCmd
      atom_value concrete_atom_guard run_cmd x c y d.
  Proof.
    intros x c y d Hxy Hxd Hyc Hconf tail rho st.
    repeat rewrite eval_two_lets.
    destruct (exec_two_independent x c y d rho st Hxd Hyc Hconf)
      as [vx [vy [final [Hforward Hreverse]]]].
    rewrite Hforward, Hreverse.
    apply concrete_eval_env_ext.
    now apply bind_distinct_commute.
  Qed.

  Definition TypeEnv := Id -> option CType.
  Definition RegionEnv := nat -> option CType.

  Definition type_bind (gamma : TypeEnv) (x : Id) (t : CType) : TypeEnv :=
    fun y => if Nat.eqb y x then Some t else gamma y.

  Definition atom_type (gamma : TypeEnv) (a : CAtom) : option CType :=
    match a with
    | CAVar x => gamma x
    | CAInt _ => Some CTInt
    | CABool _ => Some CTBool
    | CAUnit => Some CTUnit
    end.

  Definition pure_type (gamma : TypeEnv) (p : CPure) : option CType :=
    match p with
    | CPCopy a => atom_type gamma a
    | CPAdd a b | CPSub a b | CPMul a b =>
        match atom_type gamma a, atom_type gamma b with
        | Some CTInt, Some CTInt => Some CTInt
        | _, _ => None
        end
    | CPEq a b =>
        match atom_type gamma a, atom_type gamma b with
        | Some t, Some u => if ctype_eqb t u then Some CTBool else None
        | _, _ => None
        end
    | CPLt a b =>
        match atom_type gamma a, atom_type gamma b with
        | Some CTInt, Some CTInt => Some CTBool
        | _, _ => None
        end
    | CPNot a =>
        match atom_type gamma a with
        | Some CTBool => Some CTBool
        | _ => None
        end
    end.

  Definition infer_cmd (gamma : TypeEnv) (sigma : RegionEnv) (c : CCmd)
      : option (CType * CEffect) :=
    match c with
    | CCPure p =>
        match pure_type gamma p with
        | Some t => Some (t, command_effect c)
        | None => None
        end
    | CCGet r =>
        match sigma r with
        | Some t => Some (t, command_effect c)
        | None => None
        end
    | CCPut r a =>
        match sigma r, atom_type gamma a with
        | Some t, Some u =>
            if ctype_eqb t u then Some (CTUnit, command_effect c) else None
        | _, _ => None
        end
    | CCEmit a =>
        match atom_type gamma a with
        | Some _ => Some (CTUnit, command_effect c)
        | None => None
        end
    end.

  Theorem infer_cmd_effect_exact : forall gamma sigma c t e,
    infer_cmd gamma sigma c = Some (t, e) -> e = command_effect c.
  Proof.
    intros gamma sigma c t e Hinfer.
    destruct c as [p|r|r a|a]; simpl in Hinfer.
    - destruct (pure_type gamma p); inversion Hinfer; reflexivity.
    - destruct (sigma r); inversion Hinfer; reflexivity.
    - destruct (sigma r) as [tr|] eqn:Hs;
      destruct (atom_type gamma a) as [ta|] eqn:Ha; try discriminate.
      destruct (ctype_eqb tr ta); inversion Hinfer; reflexivity.
    - destruct (atom_type gamma a); inversion Hinfer; reflexivity.
  Qed.

  Definition checker_legal (gamma : TypeEnv) (sigma : RegionEnv)
      (x : Id) (c : CCmd) (y : Id) (d : CCmd) : Prop :=
    exists tx ty ex ey,
      infer_cmd gamma sigma c = Some (tx, ex) /\
      infer_cmd (type_bind gamma x tx) sigma d = Some (ty, ey) /\
      x <> y /\
      command_mentions x d = false /\
      command_mentions y c = false /\
      effects_conflict ex ey = false.

  Theorem checker_legal_commutes : forall gamma sigma x c y d,
    checker_legal gamma sigma x c y d ->
    @CommandsCommute CValue CState CAtom CCmd
      atom_value concrete_atom_guard run_cmd x c y d.
  Proof.
    intros gamma sigma x c y d Hlegal.
    destruct Hlegal as [tx [ty [ex [ey [Hc [Hd [Hxy [Hxd [Hyc Hconf]]]]]]]]].
    pose proof (@infer_cmd_effect_exact gamma sigma c tx ex Hc) as Hex.
    pose proof (@infer_cmd_effect_exact (type_bind gamma x tx) sigma d ty ey Hd) as Hey.
    subst ex ey.
    now apply independent_commands_commute.
  Qed.

  Definition CExpr := @Expr CAtom CCmd.

  Theorem concrete_core_checker_sound :
    forall (gamma : TypeEnv) (sigma : RegionEnv)
      (candidates : CExpr -> list Pair)
      (orient_expr : Pair -> bool -> CExpr -> CExpr)
      (decode_expr : Pair -> CExpr -> option bool),
      (forall q b e, decode_expr q (orient_expr q b e) = Some b) ->
      (forall q r b e, pair_disjoint q r ->
         decode_expr r (orient_expr q b e) = decode_expr r e) ->
      forall source target bits desc,
        @CoreAccepted CAtom CCmd (checker_legal gamma sigma)
          candidates orient_expr source target bits desc ->
        (forall rho st,
           @eval CValue CState CAtom CCmd atom_value concrete_atom_guard run_cmd
             source rho st =
           @eval CValue CState CAtom CCmd atom_value concrete_atom_guard run_cmd
             target rho st) /\
        desc = @canonical_descriptor CAtom CCmd candidates source bits /\
        NonOverlapping desc /\
        @extract_many CExpr decode_expr desc target = Some bits.
  Proof.
    intros gamma sigma candidates orient_expr decode_expr Hest Hframe
      source target bits desc Hacc.
    exact (@core_checker_sound CValue CState CAtom CCmd
      atom_value concrete_atom_guard run_cmd
      (checker_legal gamma sigma) (@checker_legal_commutes gamma sigma)
      candidates orient_expr decode_expr Hest Hframe
      source target bits desc Hacc).
  Qed.

  Definition gamma_empty : TypeEnv := fun _ => None.
  Definition sigma_two : RegionEnv :=
    fun r => if Nat.eqb r 0 then Some CTInt
             else if Nat.eqb r 1 then Some CTInt
             else None.

  Example distinct_get_put_is_checker_legal :
    checker_legal gamma_empty sigma_two 10 (CCGet 0) 11
      (CCPut 1 (CAInt 7)).
  Proof.
    unfold checker_legal, gamma_empty, sigma_two, infer_cmd, type_bind.
    exists CTInt, CTUnit,
      (command_effect (CCGet 0)), (command_effect (CCPut 1 (CAInt 7))).
    repeat split; simpl; try reflexivity; discriminate.
  Qed.

  Example same_region_get_put_conflicts :
    commands_conflict (CCGet 0) (CCPut 0 (CAInt 7)) = true.
  Proof. reflexivity. Qed.

End ConcreteEffectAdequacy.

Check ConcreteEffectAdequacy.infer_cmd_effect_exact.
Check ConcreteEffectAdequacy.run_pair_commutes_same_env.
Check ConcreteEffectAdequacy.independent_commands_commute.
Check ConcreteEffectAdequacy.checker_legal_commutes.
Check ConcreteEffectAdequacy.concrete_core_checker_sound.
Check ConcreteEffectAdequacy.distinct_get_put_is_checker_legal.
Check ConcreteEffectAdequacy.same_region_get_put_conflicts.
Print Assumptions ConcreteEffectAdequacy.infer_cmd_effect_exact.
Print Assumptions ConcreteEffectAdequacy.checker_legal_commutes.
Print Assumptions ConcreteEffectAdequacy.concrete_core_checker_sound.

(** Heterogeneous footprint composition.  Unlike the earlier pair witness,
    this layer admits singleton, pair, and future finite-footprint carriers. *)
Section HeterogeneousCarrierComposition.
  Context {Site CarrierState : Type}.
  Variable footprint : Site -> list Id.

  Definition sites_disjoint (q r : Site) : Prop :=
    forall x, In x (footprint q) -> ~ In x (footprint r).

  Inductive SitesNonOverlapping : list Site -> Prop :=
  | SNO_nil : SitesNonOverlapping []
  | SNO_cons : forall q qs,
      (forall r, In r qs -> sites_disjoint q r) ->
      SitesNonOverlapping qs ->
      SitesNonOverlapping (q :: qs).

  Variable orient_site : Site -> bool -> CarrierState -> CarrierState.
  Variable decode_site : Site -> CarrierState -> option bool.

  Hypothesis site_orientation_establishes : forall q b s,
    decode_site q (orient_site q b s) = Some b.

  Hypothesis site_orientation_frames : forall q r b s,
    sites_disjoint q r ->
    decode_site r (orient_site q b s) = decode_site r s.

  Fixpoint orient_sites (qs : list Site) (bits : list bool)
      (s : CarrierState) : option CarrierState :=
    match qs, bits with
    | [], [] => Some s
    | q :: qs', b :: bits' =>
        match orient_sites qs' bits' s with
        | Some s' => Some (orient_site q b s')
        | None => None
        end
    | _, _ => None
    end.

  Fixpoint decode_sites (qs : list Site) (s : CarrierState)
      : option (list bool) :=
    match qs with
    | [] => Some []
    | q :: qs' =>
        match decode_site q s, decode_sites qs' s with
        | Some b, Some bits => Some (b :: bits)
        | _, _ => None
        end
    end.

  Lemma decode_sites_frame : forall q qs b s,
    (forall r, In r qs -> sites_disjoint q r) ->
    decode_sites qs (orient_site q b s) = decode_sites qs s.
  Proof.
    intros q qs. induction qs as [|r rs IH]; intros b s Hdis; simpl.
    - reflexivity.
    - rewrite site_orientation_frames by (apply Hdis; simpl; auto).
      rewrite IH.
      + reflexivity.
      + intros r' Hin. apply Hdis. simpl; auto.
  Qed.

  Theorem heterogeneous_exact_extraction : forall qs bits s target,
    SitesNonOverlapping qs ->
    orient_sites qs bits s = Some target ->
    decode_sites qs target = Some bits.
  Proof.
    intros qs bits. revert qs.
    induction bits as [|b bits IH]; intros qs s target Hno Horient.
    - destruct qs as [|q qs]; simpl in Horient;
        [inversion Horient; reflexivity|discriminate].
    - destruct qs as [|q qs]; simpl in Horient; [discriminate|].
      inversion Hno as [|? ? Hdis Htail]; subst.
      destruct (orient_sites qs bits s) as [mid|] eqn:Hmid;
        try discriminate.
      inversion Horient; subst target; clear Horient.
      simpl. rewrite site_orientation_establishes.
      rewrite decode_sites_frame by exact Hdis.
      rewrite (IH qs s mid Htail Hmid).
      reflexivity.
  Qed.

  Definition site_descriptor (candidates : list Site) (payload_length : nat)
      : list Site := firstn payload_length candidates.

  Theorem heterogeneous_descriptor_value_independent :
    forall candidates (bits1 bits2 : list bool),
      length bits1 = length bits2 ->
      site_descriptor candidates (length bits1) =
      site_descriptor candidates (length bits2).
  Proof. intros; now rewrite H. Qed.
End HeterogeneousCarrierComposition.

Module ConcreteCarrierLibraryAdequacy.
  Import ConcreteEffectAdequacy.

  Lemma int_binary_add_comm : forall v w,
    int_binary Z.add v w = int_binary Z.add w v.
  Proof.
    intros v w. destruct v as [x|b|]; destruct w as [y|c|];
      simpl; try reflexivity.
    now rewrite Z.add_comm.
  Qed.

  Lemma int_binary_mul_comm : forall v w,
    int_binary Z.mul v w = int_binary Z.mul w v.
  Proof.
    intros v w. destruct v as [x|b|]; destruct w as [y|c|];
      simpl; try reflexivity.
    now rewrite Z.mul_comm.
  Qed.

  Lemma value_eqb_sym : forall v w,
    value_eqb v w = value_eqb w v.
  Proof.
    intros v w. destruct v as [x|b|]; destruct w as [y|c|];
      simpl; try reflexivity.
    - now rewrite Z.eqb_sym.
    - destruct b, c; reflexivity.
  Qed.

  Theorem add_operand_orientation_preserves_pure_value : forall a b rho,
    pure_value (CPAdd a b) rho = pure_value (CPAdd b a) rho.
  Proof. intros. simpl. apply int_binary_add_comm. Qed.

  Theorem mul_operand_orientation_preserves_pure_value : forall a b rho,
    pure_value (CPMul a b) rho = pure_value (CPMul b a) rho.
  Proof. intros. simpl. apply int_binary_mul_comm. Qed.

  Theorem eq_operand_orientation_preserves_pure_value : forall a b rho,
    pure_value (CPEq a b) rho = pure_value (CPEq b a) rho.
  Proof. intros. simpl. now rewrite value_eqb_sym. Qed.

  Theorem add_operand_orientation_preserves_command : forall a b rho st,
    run_cmd (CCPure (CPAdd a b)) rho st =
    run_cmd (CCPure (CPAdd b a)) rho st.
  Proof. intros. simpl. now rewrite int_binary_add_comm. Qed.

  Theorem mul_operand_orientation_preserves_command : forall a b rho st,
    run_cmd (CCPure (CPMul a b)) rho st =
    run_cmd (CCPure (CPMul b a)) rho st.
  Proof. intros. simpl. now rewrite int_binary_mul_comm. Qed.

  Theorem eq_operand_orientation_preserves_command : forall a b rho st,
    run_cmd (CCPure (CPEq a b)) rho st =
    run_cmd (CCPure (CPEq b a)) rho st.
  Proof. intros. simpl. now rewrite value_eqb_sym. Qed.

  Lemma int_identity_preserves_type : forall gamma a,
    atom_type gamma a = Some CTInt ->
    pure_type gamma (CPCopy a) = pure_type gamma (CPAdd a (CAInt 0)).
  Proof. intros gamma a H. simpl. now rewrite H. Qed.

  Lemma bool_identity_preserves_type : forall gamma a,
    atom_type gamma a = Some CTBool ->
    pure_type gamma (CPCopy a) = pure_type gamma (CPEq a (CABool true)).
  Proof. intros gamma a H. simpl. now rewrite H. Qed.

  Theorem int_identity_orientation_preserves_pure_value : forall a rho z,
    atom_value a rho = CVInt z ->
    pure_value (CPCopy a) rho = pure_value (CPAdd a (CAInt 0)) rho.
  Proof. intros a rho z H. simpl. rewrite H. simpl. now rewrite Z.add_0_r. Qed.

  Theorem bool_identity_orientation_preserves_pure_value : forall a rho b,
    atom_value a rho = CVBool b ->
    pure_value (CPCopy a) rho = pure_value (CPEq a (CABool true)) rho.
  Proof. intros a rho b H. simpl. rewrite H. destruct b; reflexivity. Qed.

  Theorem int_identity_orientation_preserves_command : forall a rho st z,
    atom_value a rho = CVInt z ->
    run_cmd (CCPure (CPCopy a)) rho st =
    run_cmd (CCPure (CPAdd a (CAInt 0))) rho st.
  Proof.
    intros. simpl. rewrite H. simpl. now rewrite Z.add_0_r.
  Qed.

  Theorem bool_identity_orientation_preserves_command : forall a rho st b,
    atom_value a rho = CVBool b ->
    run_cmd (CCPure (CPCopy a)) rho st =
    run_cmd (CCPure (CPEq a (CABool true))) rho st.
  Proof. intros. simpl. rewrite H. destruct b; reflexivity. Qed.
End ConcreteCarrierLibraryAdequacy.

Section NormalizationBoundary.
  Context {Program : Type}.
  Variable orient_bit : bool -> Program.
  Variable normalize_program : Program -> Program.
  Variable decode_bit : Program -> option bool.

  Theorem canonicalization_collapse_precludes_exact_decoding :
    normalize_program (orient_bit false) =
      normalize_program (orient_bit true) ->
    decode_bit (normalize_program (orient_bit false)) = Some false ->
    decode_bit (normalize_program (orient_bit true)) = Some true ->
    False.
  Proof.
    intros Hcollapse Hfalse Htrue.
    rewrite Hcollapse in Hfalse.
    rewrite Htrue in Hfalse.
    discriminate.
  Qed.

  Corollary no_exact_decoder_after_collapsing_normalization :
    normalize_program (orient_bit false) =
      normalize_program (orient_bit true) ->
    ~ (forall b, decode_bit (normalize_program (orient_bit b)) = Some b).
  Proof.
    intros Hcollapse Hall.
    eapply canonicalization_collapse_precludes_exact_decoding.
    - exact Hcollapse.
    - apply Hall.
    - apply Hall.
  Qed.
End NormalizationBoundary.

Check heterogeneous_exact_extraction.
Check heterogeneous_descriptor_value_independent.
Check ConcreteCarrierLibraryAdequacy.add_operand_orientation_preserves_command.
Check ConcreteCarrierLibraryAdequacy.mul_operand_orientation_preserves_command.
Check ConcreteCarrierLibraryAdequacy.eq_operand_orientation_preserves_command.
Check ConcreteCarrierLibraryAdequacy.int_identity_preserves_type.
Check ConcreteCarrierLibraryAdequacy.bool_identity_preserves_type.
Check ConcreteCarrierLibraryAdequacy.int_identity_orientation_preserves_command.
Check ConcreteCarrierLibraryAdequacy.bool_identity_orientation_preserves_command.
Check canonicalization_collapse_precludes_exact_decoding.
Check no_exact_decoder_after_collapsing_normalization.
Print Assumptions heterogeneous_exact_extraction.
Print Assumptions ConcreteCarrierLibraryAdequacy.add_operand_orientation_preserves_command.
Print Assumptions ConcreteCarrierLibraryAdequacy.eq_operand_orientation_preserves_command.
Print Assumptions ConcreteCarrierLibraryAdequacy.int_identity_orientation_preserves_command.
Print Assumptions ConcreteCarrierLibraryAdequacy.bool_identity_orientation_preserves_command.
Print Assumptions no_exact_decoder_after_collapsing_normalization.
