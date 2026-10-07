/* Source equivalent of the three pinned CoreInputView3 method replacements.
 * These desktop calls decline Windows' on-screen input pane without throwing.
 * The shipped patch preserves each existing prologue and its unwind metadata.
 */
typedef int HRESULT;
typedef unsigned char boolean;
#define S_OK ((HRESULT)0)
#define E_POINTER ((HRESULT)0x80004003)

HRESULT __stdcall desktop_TryShow(void *view, boolean *result)
{
    if (!result) return E_POINTER;
    *result = 0;
    return S_OK;
}

HRESULT __stdcall desktop_TryShowWithKind(void *view, int kind, boolean *result)
{
    if (!result) return E_POINTER;
    *result = 0;
    return S_OK;
}

HRESULT __stdcall desktop_TryHide(void *view, boolean *result)
{
    if (!result) return E_POINTER;
    *result = 0;
    return S_OK;
}
