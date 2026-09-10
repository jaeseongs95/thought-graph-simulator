"""참조 선택기의 수치·분기 검증. CTA 전체의 보안/건전성 시험이 아니다."""
import math
import random
import unittest
from reference_router import Option, distribution, js_bits, select, TRANSITION_ALPHABET

class RouterTests(unittest.TestCase):
    def test_01_identical(self):
        self.assertAlmostEqual(js_bits((.2,.8),(.2,.8)),0.)
    def test_02_disjoint(self):
        self.assertAlmostEqual(js_bits((1.,0.),(0.,1.)),1.)
    def test_03_symmetry(self):
        self.assertAlmostEqual(js_bits((.2,.8),(.7,.3)),js_bits((.7,.3),(.2,.8)))
    def test_04_empty_distribution(self):
        with self.assertRaises(ValueError): distribution(())
    def test_05_negative_distribution(self):
        with self.assertRaises(ValueError): distribution((-1.,2.))
    def test_06_nonnormalized(self):
        with self.assertRaises(ValueError): distribution((.2,.2))
    def test_07_nan(self):
        with self.assertRaises(ValueError): distribution((math.nan,1.))
    def test_08_alphabet_mismatch(self):
        with self.assertRaises(ValueError): js_bits((1.,),(1.,0.))
    def test_09_empty_admissible(self):
        d=select([Option("bad",100.,False)],None,0.,False)
        self.assertIsNone(d.operator_id)
    def test_10_forbidden_excluded(self):
        d=select([Option("bad",100.,False),Option("good",.1)],None,0.,False)
        self.assertEqual(d.operator_id,"good")
    def test_11_zero_weight_exact_fallback(self):
        self.assertEqual(select([Option("a",.2),Option("b",.3)],None,0.,True).operator_id,"b")
    def test_12_untrusted_ignores_missing(self):
        self.assertEqual(select([Option("a",.2),Option("b",.3)],None,.5,False).operator_id,"b")
    def test_13_active_requires_distribution(self):
        with self.assertRaises(ValueError): select([Option("a",.2)],(1.,0.),.5,True)
    def test_14_ties_deterministic(self):
        self.assertEqual(select([Option("b",.2),Option("a",.2)],None,0.,False).operator_id,"a")
    def test_15_change_of_choice(self):
        opts=[Option("a",.60,True,(.8,.1,.1)),Option("b",.56,True,(.1,.8,.1))]
        self.assertEqual(select(opts,(.1,.8,.1),.2,True).operator_id,"b")
    def test_16_margin_preserved(self):
        opts=[Option("a",.8,True,(1.,0.)),Option("b",.5,True,(0.,1.))]
        self.assertEqual(select(opts,(0.,1.),.2,True).operator_id,"a")
    def test_17_duplicate_id(self):
        with self.assertRaises(ValueError): select([Option("a",.1),Option("a",.2)],None,0.,False)
    def test_18_negative_weight(self):
        with self.assertRaises(ValueError): select([Option("a",.1)],None,-1.,False)
    def test_19_randomized_surrogate_bound(self):
        rng=random.Random(20260910)
        def prob():
            p=[rng.random() for _ in range(5)]; s=sum(p)
            return tuple(x/s for x in p)
        for _ in range(2000):
            lam=rng.random(); q=prob()
            opts=[Option(str(k),rng.uniform(-1,1),True,prob()) for k in range(4)]
            selected=select(opts,q,lam,True).operator_id
            u={x.operator_id:x.base_utility for x in opts}
            self.assertLessEqual(max(u.values())-u[selected],lam+1e-12)
            for x in opts: self.assertTrue(0.<=js_bits(x.predicted_transition,q)<=1.)
    def test_20_input_order_invariance(self):
        opts=[Option("b",.5,True,(.3,.7)),Option("a",.5,True,(.3,.7))]
        self.assertEqual(select(opts,(.5,.5),.3,True).operator_id,
                         select(list(reversed(opts)),(.5,.5),.3,True).operator_id)


    def test_21_permission_type(self):
        for flag in ("false", 0, 1, None):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                select([Option("a", .5, flag)], None, 0, False)
    def test_22_trust_type(self):
        for flag in ("false", 0, 1, None):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                select([Option("a", .5)], None, 0, flag)
    def test_23_nonfinite_weights(self):
        for x in (math.inf, -math.inf, math.nan):
            with self.subTest(x=x), self.assertRaises(ValueError):
                select([Option("a", .5)], None, x, False)
    def test_24_nonnumeric_weights(self):
        for x in ("0.1", True, None):
            with self.subTest(x=x), self.assertRaises(ValueError):
                select([Option("a", .5)], None, x, False)
    def test_25_invalid_utilities(self):
        for x in (math.inf, math.nan, "0.1", True):
            with self.subTest(x=x), self.assertRaises(ValueError):
                select([Option("a", x)], None, 0, False)
    def test_26_blank_id(self):
        for key in ("", " ", None, 1):
            with self.subTest(key=key), self.assertRaises(ValueError):
                select([Option(key, .5)], None, 0, False)
    def test_27_missing_prior(self):
        with self.assertRaises(ValueError):
            select([Option("a", .5, True, (1.,))], None, .5, True)
    def test_28_missing_one_effect(self):
        with self.assertRaises(ValueError):
            select([Option("a", .5, True, (1.,)), Option("b", .4)], (1.,), .5, True)
    def test_29_invalid_prior_ignored_on_fallback(self):
        opts=[Option("a", .5, True, (math.nan,))]
        for strength, trusted in ((0, True), (.5, False)):
            self.assertEqual(select(opts, (math.nan,), strength, trusted).operator_id,"a")
    def test_30_invalid_disallowed_effect_ignored(self):
        d=select([Option("a", .5, True, (1.,)), Option("b", math.nan, False, (math.nan,))], (1.,), .2, True)
        self.assertEqual(d.operator_id,"a")
    def test_31_subnormal_probability(self):
        self.assertTrue(math.isfinite(js_bits((5e-324,1.),(0.,1.))))
        self.assertAlmostEqual(js_bits((5e-324,1.),(5e-324,1.)),0.)
    def test_32_score_overflow_rejected(self):
        with self.assertRaises(ValueError):
            select([Option("a", -1.7e308, True, (1.,0.))], (0.,1.), 1.7e308, True)
    def test_33_probability_type(self):
        for values in ((True, False), ("0.2", "0.8"), None, "1"):
            with self.subTest(values=values), self.assertRaises(ValueError): distribution(values)
    def test_34_probability_overflow(self):
        with self.assertRaises(ValueError): distribution((1.7e308,1.7e308))
    def test_35_canonical_alphabet(self):
        self.assertEqual(len(TRANSITION_ALPHABET),93)
        self.assertEqual(len(set(TRANSITION_ALPHABET)),93)
        self.assertEqual(TRANSITION_ALPHABET[0],"pass_A0_D0_M0")
        self.assertEqual(TRANSITION_ALPHABET[89],"pass_A4_D5+_M2")
        self.assertEqual(TRANSITION_ALPHABET[90:],("reject","unknown","stop"))
    def test_36_full_alphabet_equivalence(self):
        labels=("pass_A1_D2_M0","pass_A1_D1_M1","reject")
        p=[0.]*93; q=[0.]*93
        for label,a,b in zip(labels,(.8,.1,.1),(.1,.8,.1)):
            p[TRANSITION_ALPHABET.index(label)]=a; q[TRANSITION_ALPHABET.index(label)]=b
        self.assertAlmostEqual(js_bits(p,q),js_bits((.8,.1,.1),(.1,.8,.1)))
    def test_37_exact_score_fallback(self):
        opts=[Option("a",.7),Option("b",-.2)]
        d=select(opts,None,4.,False)
        self.assertEqual(d.scores,{"a":.7,"b":-.2})
        self.assertEqual(d.reason,"BASELINE")
    def test_38_empty_options(self):
        d=select([],None,.5,True)
        self.assertIsNone(d.operator_id)
        self.assertEqual(d.reason,"NO_ADMISSIBLE_OPERATOR")
    def test_39_wrong_option_object(self):
        with self.assertRaises(ValueError): select(["not_option"],None,0,False)
    def test_40_no_silent_normalization(self):
        p=(.1,.2,.70000000001)
        self.assertEqual(distribution(p),p)
        with self.assertRaises(ValueError): distribution((.1,.2,.700000001))

if __name__ == "__main__": unittest.main(verbosity=2)
