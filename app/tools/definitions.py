TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "select_category",
            "description": "Ask the engineer to select the category of the service before searching. Call this before search_services when the item is a service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "The service item the engineer wants to find.",
                    }
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_services",
            "description": "Search for construction services in the database. Use 2-3 simple keywords in Portuguese without accents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "2-3 simple keywords to search. Example: 'pintura parede', 'tomada embutir', 'mao francesa'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search for products in the catalog by supply name. Use 2-3 simple keywords in Portuguese without accents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "2-3 simple keywords to search. Example: 'tinta latex', 'tomada 20A', 'cabo cobre'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_selection",
            "description": "Register the engineer's selection (service or product) in the list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["service", "product"],
                    },
                    "description": {
                        "type": "string",
                        "description": "Exact description of the selected item.",
                    },
                },
                "required": ["type", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_list",
            "description": "Finish the process and return the complete list. Call only when all services and supplies have been processed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation": {
                        "type": "string",
                        "description": "Always pass 'yes' to confirm finishing.",
                    }
                },
                "required": ["confirmation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_item_list",
            "description": "Call this FIRST when the engineer sends a list of items. Register all items so none are forgotten.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "All items from the engineer's list, exactly as written.",
                    }
                },
                "required": ["items"],
            },
        },
    },
]