from typing import List, Dict, Any, Optional, Callable

from pathlib import Path

from canals.pipeline import (
    Pipeline as CanalsPipeline,
    PipelineError,
    load_pipelines as load_canals_pipelines,
    save_pipelines as save_canals_pipelines,
)

from haystack.preview.document_stores.protocols import DocumentStore
from haystack.preview.document_stores.mixins import DocumentStoreAwareMixin


class NotADocumentStoreError(PipelineError):
    pass


class NoSuchDocumentStoreError(PipelineError):
    pass


class Pipeline(CanalsPipeline):
    """
    Haystack Pipeline is a thin wrapper over Canals' Pipelines to add support for DocumentStores.
    """

    def __init__(self):
        super().__init__()
        self._document_stores_connections = {}
        self._document_stores: Dict[str, DocumentStore] = {}

    def add_document_store(self, name: str, document_store: DocumentStore) -> None:
        """
        Make a DocumentStore available to all nodes of this pipeline.

        :param name: the name of the DocumentStore.
        :param document_store: the DocumentStore object.
        :returns: None
        """
        if not getattr(document_store, "__haystack_document_store__", False):
            raise NotADocumentStoreError(
                f"'{type(document_store).__name__}' is not decorated with @document_store, "
                "so it can't be added to the pipeline with Pipeline.add_document_store()."
            )
        self._document_stores[name] = document_store

    def list_document_stores(self) -> List[str]:
        """
        Returns a dictionary with all the DocumentStores that are attached to this Pipeline.

        :returns: a dictionary with all the DocumentStores attached to this Pipeline.
        """
        return list(self._document_stores.keys())

    def get_document_store(self, name: str) -> DocumentStore:
        """
        Returns the DocumentStore associated with the given name.

        :param name: the name of the DocumentStore
        :returns: the DocumentStore
        """
        try:
            return self._document_stores[name]
        except KeyError as e:
            raise NoSuchDocumentStoreError(f"No DocumentStore named '{name}' was added to this pipeline.") from e

    def add_component(self, name: str, instance: Any, document_store: Optional[str] = None) -> None:
        """
        Make this component available to the pipeline. Components are not connected to anything by default:
        use `Pipeline.connect()` to connect components together.

        Component names must be unique, but component instances can be reused if needed.

        If `document_store` is not None, the pipeline will also connect this component to the requested DocumentStore.
        Note that only components that inherit from DocumentStoreAwareMixin can be connected to DocumentStores.

        :param name: the name of the component.
        :param instance: the component instance.
        :param document_store: the DocumentStore this component needs access to, if any.
        :raises ValueError: if:
            - a component with the same name already exists
            - a component requiring a DocumentStore didn't receive it
            - a component that didn't expect a DocumentStore received it
        :raises PipelineValidationError: if the given instance is not a component
        :raises NoSuchDocumentStoreError: if the given DocumentStore name is not known to the pipeline
        """
        if isinstance(instance, DocumentStoreAwareMixin):
            if document_store and instance.document_store:
                raise ValueError(
                    f"Component '{name}' is already connected to Document "
                    f"Store '{self._document_stores_connections[name]}'."
                )

            if not document_store and not instance.document_store:
                raise ValueError(f"Component '{name}' needs a DocumentStore.")

            if document_store not in self._document_stores:
                raise NoSuchDocumentStoreError(
                    f"DocumentStore named '{document_store}' not found. "
                    f"Add it with 'pipeline.add_document_store('{document_store}', <the DocumentStore instance>)'."
                )

            if not instance.document_store:
                self._document_stores_connections[name] = document_store
                instance.document_store = self._document_stores[document_store]
                instance._document_store_name = document_store

        elif document_store:
            raise ValueError(f"Component '{name}' doesn't support DocumentStores.")

        super().add_component(name, instance)


import json
from copy import copy
from haystack.preview.document_stores.decorator import document_store
from canals.pipeline.save_load import (
    marshal_pipelines as marshal_canals_pipelines,
    _unmarshal_pipelines as _unmarshal_canals_pipelines,
    _unmarshal_components as _unmarshal_canals_components,
)


def _json_writer(data: Dict[str, Any], stream):
    return json.dump(data, stream, indent=4)


def save_pipelines(pipelines: Dict[str, Pipeline], path: Path, writer=_json_writer) -> None:
    """
    Converts a dictionary of named Pipelines into a JSON file.

    Args:
        pipelines: dictionary of {name: pipeline_object}
        path: where to write the resulting file
        writer: which function to use to write the dictionary to a file.
            Use this parameter to dump to a different format like YAML, TOML, HCL, etc.

    Returns:
        None
    """
    data = marshal_pipelines(pipelines=pipelines)
    with open(path, "w", encoding="utf-8") as file:
        writer(data, file)


def load_pipelines(path: Path, reader=json.load) -> Dict[str, Pipeline]:
    """
    Loads the content of a JSON file generated by `save_pipelines()` into
    a dictionary of named Pipelines.

    Args:
        path: where to read the file from
        reader: which function to use to read the dictionary to a file.
            Use this parameter to load from a different format like YAML, TOML, HCL, etc.

    Returns:
        The pipelines as a dictionary of `{"pipeline-name": <pipeline object>}`
    """
    with open(path, "r", encoding="utf-8") as handle:
        data = reader(handle)
    return unmarshal_pipelines(data)


def marshal_pipelines(pipelines: Dict[str, Pipeline]) -> Dict[str, Any]:
    """
    Converts a dictionary of named Pipelines into a Python dictionary that can be
    written to a JSON file.

    In case there are different component instances, meaning components with a different
    hash, and an identical name they are suffixed with an underscore and an incrementing number.
    This way we can be sure that there is no confusion when loading back the Pipelines from file.
    Obviously names will be different when unmarshaling but Pipelines' behaviour won't change.

    Args:
        pipelines: A dictionary of `{"pipeline-name": <pipeline object>}`

    Returns:
        A Python dictionary representing the Pipelines objects above, that can be written to JSON and can be reused to
        recreate the original Pipelines.
    """
    marshalled_pipelines = marshal_canals_pipelines(pipelines)

    marshalled_stores = {}
    for pipeline_name, pipeline in pipelines.items():
        store_connections = copy(pipelines[pipeline_name]._document_stores_connections)
        for store_name, store in pipeline._document_stores.items():
            marshalled_store = store.to_dict()

            if any(marshalled_store["hash"] == s["hash"] for s in marshalled_stores.values()):
                # This store is already present, we'll reuse it
                continue
            del marshalled_store["hash"]

            # Avoiding name collisions across different stores with the same name
            unique_store_name = store_name
            i = 0
            while unique_store_name in marshalled_stores:
                unique_store_name = store_name + "_" + str(i)
                i += 1

            # Rename the connections if necessary
            if unique_store_name != store_name:
                for connection_name, connection in store_connections.items():
                    if connection == store_name:
                        store_connections[connection_name] = unique_store_name

            marshalled_stores[unique_store_name] = marshalled_store
        marshalled_pipelines["pipelines"][pipeline_name]["store_connections"] = store_connections
    marshalled_pipelines["stores"] = marshalled_stores
    return marshalled_pipelines


def unmarshal_pipelines(data: Dict[str, Any]) -> Dict[str, Pipeline]:
    """
    Loads the content of a dictionary generated by `marshal_pipelines()` into
    a dictionary of named Pipelines.

    Args:
        data: pipelines' data, as generated by `marshal_pipelines()`.

    Returns:
        The pipelines as a dictionary of `{"pipeline-name": <pipeline object>}`.
    """
    # Unmarshal stores
    stores = {}
    for store_name, store in data["stores"].items():
        cls = document_store.registry[store["type"]]
        stores[store_name] = cls.from_dict(store)

    components = _unmarshal_canals_components(data)
    for pipeline in data["pipelines"].values():
        # Reconnect stores
        store_connections = pipeline["store_connections"]
        for component_name, store_name in store_connections.items():
            components[component_name].document_store = stores[store_name]

    pipelines = _unmarshal_canals_pipelines(data, components)

    return pipelines
