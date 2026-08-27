from app.connectors.canvas.client import (
    CanvasReadOnlyClient,
)


class CanvasDiscoveryService:
    def __init__(
        self,
        canvas: CanvasReadOnlyClient,
    ):
        self._canvas = canvas

    async def list_active_courses(
        self,
    ) -> list[dict]:
        return await self._canvas.get_paginated(
            "courses",
            params={
                "enrollment_state": "active",
                "per_page": 100,
            },
        )

    #to calls GET /api/v1/courses/{course_id}/assignments
    async def list_assignments(
        self,
        course_id: str,
    ) -> list[dict]:
        return await self._canvas.get_paginated(
            f"courses/{course_id}/assignments",
            params={
                "per_page": 100,
                "order_by": "due_at",
            },
        )


    #Perform GET /api/v1/courses/{course_id}/modules to retrieve a list of modules for a specific course
    async def list_modules(
        self,
        course_id: str,
    ) -> list[dict]:
        return await self._canvas.get_paginated(
            f"courses/{course_id}/modules",
            params={
                "per_page": 100,
            },
        )

    #Perform GET /api/v1/courses/{course_id}/modules/{module_id}/items to retrieve a list of items for a specific module in a course
    async def list_module_items(
        self,
        course_id: str,
        module_id: str,
    ) -> list[dict]:
        return await self._canvas.get_paginated(
            (
                f"courses/{course_id}/modules/"
                f"{module_id}/items"
            ),
            params={
                "per_page": 100,
            },
        )

    #Perform GET /api/v1/files/{file_id} to retrieve metadata for a specific file in Canvas
    async def get_file_metadata(
        self,
        course_id: str,
        file_id: str,
    ) -> dict:
        result = await self._canvas.get_json(
            (
                f"courses/{course_id}/files/"
                f"{file_id}"
            )
        )

        if not isinstance(result, dict):
            raise TypeError(
                "Expected Canvas file metadata "
                "to be an object"
            )

        return result

    #Perform GET /api/v1/courses/{course_id}/pages/{page_url}
    async def get_page(
        self,
        course_id: str,
        page_url: str,
    ) -> dict:
        result = await self._canvas.get_json(
            (
                f"courses/{course_id}/pages/"
                f"{page_url}"
            )
        )

        if not isinstance(result, dict):
            raise TypeError(
                "Expected Canvas page to be an object"
            )

        return result