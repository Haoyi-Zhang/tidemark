# Cubic coefficient consumer

Source: fontTools 4.60.1, `Lib/fontTools/misc/bezierTools.py`,
`calcCubicParameters`, lines 890-901:
https://github.com/fonttools/fonttools/blob/4.60.1/Lib/fontTools/misc/bezierTools.py#L890-L901
Retrieved from the upstream raw source on 2026-10-24. The upstream
`calcCubicBounds` (lines 402-415) and `splitCubic` (lines 540-547) consume
these coefficients. This is an upstream-derived arithmetic case, not an
independent deployment or maintenance incident.

`bezier_coefficients.py` preserves the eight scalar coefficient equations.
Tuple unpacking is replaced by eight annotated integer parameters and the
tuple return by an explicitly owned `which=0..7` scalar selection consumer.
The independent x/y equations are grouped by coordinate. Constants 3.0 become
3: on the tested binary control coordinates every coefficient is integral and
exactly representable in binary64; no general floating-point refinement is
claimed. No capacity quota or dead binding is added. The test enumerates all
256 binary 2D control polygons and all eight requested coefficients (2,048
inputs). An expanded polynomial coefficient oracle, not the same recurrence,
checks the source and both IR interpreters. Native range admission covers the
whole declared box, but this case does not claim new LLVM execution.

The consumer accepts a target only if the message and all eight selectable
coefficients refer to that complete target. A controlled return-field change
is deliberately rehashed: local extraction still succeeds but a coefficient
changes. Both whole-target checkers reject it. This is a designed omission
test, not a discovered bug in an external watermarker. Existing simple
selectors receive the same source, frame and complete-replay checks; all
capacity rejections are retained.

The adapted equations are distributed under the upstream MIT license:

Copyright (c) 2017 Just van Rossum

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
