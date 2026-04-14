import requests
from typing import Dict, List, Optional
def fetch_all_groups_hierarchy(
  base_url: str,
  realm: str,
  access_token: str,
  page_size: int = 100,
  verify_ssl: bool = True,
  timeout: int = 30,
) -> List[Dict]:
  """
  Fetch full Keycloak group hierarchy by recursively traversing /groups and /children.
  Args:
      base_url: e.g. "https://keycloak.example.com"
      realm: Keycloak realm name
      access_token: Admin access token (Bearer)
      page_size: Pagination size for all list calls
      verify_ssl: requests verify flag
      timeout: request timeout in seconds
  Returns:
      List of top-level groups, each with nested 'subGroups' populated.
  """
  session = requests.Session()
  session.headers.update(
      {
          "Authorization": f"Bearer {access_token}",
          "Accept": "application/json",
      }
  )
  admin_base = f"{base_url.rstrip('/')}/admin/realms/{realm}"
  def _get_paginated(url: str, extra_params: Optional[Dict] = None) -> List[Dict]:
      first = 0
      items: List[Dict] = []
      while True:
          params = {
              "first": first,
              "max": page_size,
              "briefRepresentation": "false",
              "subGroupsCount": "true",
          }
          if extra_params:
              params.update(extra_params)
          resp = session.get(url, params=params, verify=verify_ssl, timeout=timeout)
          resp.raise_for_status()
          page = resp.json() or []
          items.extend(page)
          if len(page) < page_size:
              break
          first += page_size
      return items
  def _fetch_children_recursive(group_id: str) -> List[Dict]:
      children_url = f"{admin_base}/groups/{group_id}/children"
      children = _get_paginated(children_url)
      for child in children:
          child_id = child["id"]
          child["subGroups"] = _fetch_children_recursive(child_id)
      return children
  # Top-level groups
  top_groups_url = f"{admin_base}/groups"
  top_groups = _get_paginated(
      top_groups_url,
      # Helpful in some versions; harmless if ignored
      extra_params={"populateHierarchy": "false"},
  )
  # Build full tree
  for g in top_groups:
      g["subGroups"] = _fetch_children_recursive(g["id"])
  return top_groups
if __name__ == "__main__":
  # Example usage
  KEYCLOAK_BASE_URL = "https://keycloak.example.com"
  REALM = "myrealm"
  TOKEN = "YOUR_ADMIN_ACCESS_TOKEN"
  groups_tree = fetch_all_groups_hierarchy(
      base_url=KEYCLOAK_BASE_URL,
      realm=REALM,
      access_token=TOKEN,
      page_size=100,
  )
  # Print simple summary
  print(f"Top-level groups: {len(groups_tree)}")
