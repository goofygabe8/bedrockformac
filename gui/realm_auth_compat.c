/* Source equivalent of the empty-path normalization in realm_auth_fix.py.
 * This branch runs after successful URL parsing, before the existing allocation
 * and signing code. HRESULT failures elsewhere continue to propagate normally.
 * https://www.rfc-editor.org/rfc/rfc9112.html#section-3.2.1
 */
#include <stdint.h>

void bedrock_normalize_empty_request_path(const uint16_t **path,
                                         uint32_t *path_length,
                                         uint32_t query_length,
                                         uint32_t *combined_length)
{
    static const uint16_t root_path[] = {'/', 0};
    if (*path_length == 0 && query_length == 0)
    {
        *path = root_path;
        *path_length = 1;
        *combined_length = 1;
    }
}
