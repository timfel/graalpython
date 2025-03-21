/*
 * Copyright (c) 2021, 2025, Oracle and/or its affiliates. All rights reserved.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * The Universal Permissive License (UPL), Version 1.0
 *
 * Subject to the condition set forth below, permission is hereby granted to any
 * person obtaining a copy of this software, associated documentation and/or
 * data (collectively the "Software"), free of charge and under any and all
 * copyright rights in the Software, and any and all patent rights owned or
 * freely licensable by each licensor hereunder covering either (i) the
 * unmodified Software as contributed to or provided by such licensor, or (ii)
 * the Larger Works (as defined below), to deal in both
 *
 * (a) the Software, and
 *
 * (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
 * one is included with the Software each a "Larger Work" to which the Software
 * is contributed by such licensors),
 *
 * without restriction, including without limitation the rights to copy, create
 * derivative works of, display, perform, and distribute the Software and make,
 * use, sell, offer for sale, import, export, have made, and have sold the
 * Software and the Larger Work(s), and to sublicense the foregoing rights on
 * either these or other terms.
 *
 * This license is subject to the following condition:
 *
 * The above copyright notice and either this complete permission notice or at a
 * minimum a reference to the UPL must be included in all copies or substantial
 * portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
package com.oracle.graal.python.lib;

import static com.oracle.graal.python.nodes.SpecialMethodNames.T___REPR__;
import static com.oracle.graal.python.nodes.truffle.TruffleStringMigrationHelpers.assertNoJavaString;
import static com.oracle.graal.python.runtime.exception.PythonErrorType.TypeError;

import com.oracle.graal.python.builtins.objects.object.ObjectNodes;
import com.oracle.graal.python.builtins.objects.str.PString;
import com.oracle.graal.python.builtins.objects.type.TpSlots;
import com.oracle.graal.python.builtins.objects.type.TpSlots.GetObjectSlotsNode;
import com.oracle.graal.python.builtins.objects.type.slots.TpSlotRepr.CallSlotReprNode;
import com.oracle.graal.python.nodes.ErrorMessages;
import com.oracle.graal.python.nodes.PNodeWithContext;
import com.oracle.graal.python.nodes.PRaiseNode;
import com.oracle.graal.python.runtime.exception.PException;
import com.oracle.truffle.api.HostCompilerDirectives.InliningCutoff;
import com.oracle.truffle.api.dsl.Cached;
import com.oracle.truffle.api.dsl.GenerateCached;
import com.oracle.truffle.api.dsl.GenerateInline;
import com.oracle.truffle.api.dsl.GenerateUncached;
import com.oracle.truffle.api.dsl.NeverDefault;
import com.oracle.truffle.api.dsl.Specialization;
import com.oracle.truffle.api.frame.Frame;
import com.oracle.truffle.api.frame.VirtualFrame;
import com.oracle.truffle.api.nodes.Node;
import com.oracle.truffle.api.strings.TruffleString;

/**
 * Equivalent of CPython's {@code PyObject_Repr}. Converts the object to a string using its
 * {@code __repr__} special method. Falls back to default object {@code __repr__} implementation.
 * <p>
 * The output can be either a {@link TruffleString} or a {@link PString}.
 *
 * @see PyObjectReprAsTruffleStringNode
 */
@GenerateUncached
@GenerateCached
@GenerateInline(inlineByDefault = true)
public abstract class PyObjectReprAsObjectNode extends PNodeWithContext {

    public static Object executeUncached(Object object) {
        return PyObjectReprAsObjectNodeGen.getUncached().execute(null, null, object);
    }

    public static PyObjectReprAsObjectNode getUncached() {
        return PyObjectReprAsObjectNodeGen.getUncached();
    }

    public final Object executeCached(Frame frame, Object object) {
        return execute(frame, this, object);
    }

    public abstract Object execute(Frame frame, Node inliningTarget, Object object);

    @Specialization
    static Object repr(VirtualFrame frame, Node inliningTarget, Object obj,
                    @Cached GetObjectSlotsNode getSlots,
                    @Cached CallSlotReprNode callSlot,
                    @Cached(inline = false) ObjectNodes.DefaultObjectReprNode defaultRepr,
                    @Cached PyUnicodeCheckNode checkNode,
                    @Cached PRaiseNode raiseNode) {
        TpSlots slots = getSlots.execute(inliningTarget, obj);
        if (slots.tp_repr() == null) {
            return defaultRepr.execute(frame, inliningTarget, obj);
        }
        Object result = callSlot.execute(frame, inliningTarget, slots.tp_repr(), obj);
        assertNoJavaString(result);
        if (checkNode.execute(inliningTarget, result)) {
            return result;
        } else {
            throw raiseTypeError(inliningTarget, obj, raiseNode);
        }
    }

    @InliningCutoff
    private static PException raiseTypeError(Node inliningTarget, Object obj, PRaiseNode raiseNode) {
        throw raiseNode.raise(inliningTarget, TypeError, ErrorMessages.RETURNED_NON_STRING, T___REPR__, obj);
    }

    @NeverDefault
    public static PyObjectReprAsObjectNode create() {
        return PyObjectReprAsObjectNodeGen.create();
    }
}
