# E2E: ebooks.lv “Set default settings” applies production defaults

Goal: Ensure the `/admin/ebookslv/` button **Set default settings** applies the curated production configuration in one click.

## Preconditions

- Start QA stack: `bash .github/qa/scripts/run_all.sh`
- Login credentials (defaults):
  - Admin: `admin@example.org` / `AdminTest123!`

## Steps

1. Open ebooks.lv admin landing: `http://localhost:8083/admin/ebookslv/`
2. Click **Set default settings**.
   - Confirm the UI reports success (e.g. “Defaults applied”).
3. Open View Configuration: `http://localhost:8083/admin/viewconfig`
   - Confirm:
     - Calibre-Web title is `e-books.lv` (or the value from `APP_TITLE` if set).
     - Books per page: `60`
     - Random books: `4`
     - Authors max: `0`
4. Open Basic Configuration: `http://localhost:8083/admin/config`
   - In **Default Settings for New Users**, confirm:
     - Roles: **Viewer** ON, **Change Password** ON; all other roles OFF.
     - Default UI locale: `lv` (Latviešu)
     - Default visible book languages: `all` (Show All)
   - In **Default Visibilities for New Users**, confirm ON:
     - Read and Unread
     - Category
     - Series
     - Author
     - Language
     - File formats
     - Archived
     - Books list
   - And confirm OFF:
     - Hot
     - Downloaded
     - Top Rated
     - Publisher
     - Ratings
     - Random Books
     - Detail Random Books
5. In **Feature Configuration**, confirm:
   - Embed Metadata ON
   - Enable Uploads ON
   - Anonymous browsing ON
   - Public Registration OFF
   - Magic Link Remote Login OFF
   - Reverse Proxy Auth OFF
   - Convert non-English characters in filenames OFF
6. In **Security Settings**, confirm:
   - Limit failed login attempts ON
   - Check book formats vs file content ON
   - Session protection: **Strong**
   - Password policy ON:
     - Minimum length: `8`
     - Require number/lowercase/uppercase ON
     - Require character + require special character OFF

## Expected

- Clicking **Set default settings** deterministically applies the configuration above.
- The following fields are intentionally NOT changed by this action:
  - Allowed Upload Fileformats
  - Regular Expression for Title Sorting
