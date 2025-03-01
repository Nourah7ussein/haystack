import os
from unittest.mock import patch, Mock

import pytest

from haystack.preview.components.file_converters.azure import AzureOCRDocumentConverter


class TestAzureOCRDocumentConverter:
    @pytest.mark.unit
    def test_to_dict(self):
        component = AzureOCRDocumentConverter(endpoint="test_endpoint", api_key="test_credential_key")
        data = component.to_dict()
        assert data == {
            "type": "AzureOCRDocumentConverter",
            "init_parameters": {
                "api_key": "test_credential_key",
                "endpoint": "test_endpoint",
                "id_hash_keys": [],
                "model_id": "prebuilt-read",
            },
        }

    @pytest.mark.unit
    def test_from_dict(self):
        data = {
            "type": "AzureOCRDocumentConverter",
            "init_parameters": {
                "api_key": "test_credential_key",
                "endpoint": "test_endpoint",
                "id_hash_keys": [],
                "model_id": "prebuilt-read",
            },
        }
        component = AzureOCRDocumentConverter.from_dict(data)
        assert component.endpoint == "test_endpoint"
        assert component.api_key == "test_credential_key"
        assert component.id_hash_keys == []
        assert component.model_id == "prebuilt-read"

    @pytest.mark.unit
    def test_run(self, preview_samples_path):
        with patch("haystack.preview.components.file_converters.azure.DocumentAnalysisClient") as mock_azure_client:
            mock_result = Mock(pages=[Mock(lines=[Mock(content="mocked line 1"), Mock(content="mocked line 2")])])
            mock_result.to_dict.return_value = {
                "api_version": "2023-02-28-preview",
                "model_id": "prebuilt-read",
                "content": "mocked line 1\nmocked line 2\n\f",
                "pages": [{"lines": [{"content": "mocked line 1"}, {"content": "mocked line 2"}]}],
            }
            mock_azure_client.return_value.begin_analyze_document.return_value.result.return_value = mock_result

            component = AzureOCRDocumentConverter(endpoint="test_endpoint", api_key="test_credential_key")
            output = component.run(paths=[preview_samples_path / "pdf" / "sample_pdf_1.pdf"])
            document = output["documents"][0]
            assert document.text == "mocked line 1\nmocked line 2\n\f"
            assert "raw_azure_response" in output
            assert output["raw_azure_response"][0] == {
                "api_version": "2023-02-28-preview",
                "model_id": "prebuilt-read",
                "content": "mocked line 1\nmocked line 2\n\f",
                "pages": [{"lines": [{"content": "mocked line 1"}, {"content": "mocked line 2"}]}],
            }

    @pytest.mark.integration
    @pytest.mark.skipif(
        "CORE_AZURE_CS_ENDPOINT" not in os.environ and "CORE_AZURE_CS_API_KEY" not in os.environ,
        reason="Azure credentials not available",
    )
    def test_run_with_pdf_file(self, preview_samples_path):
        component = AzureOCRDocumentConverter(
            endpoint=os.environ["CORE_AZURE_CS_ENDPOINT"], api_key=os.environ["CORE_AZURE_CS_API_KEY"]
        )
        output = component.run(paths=[preview_samples_path / "pdf" / "sample_pdf_1.pdf"])
        documents = output["documents"]
        assert len(documents) == 1
        assert "A sample PDF file" in documents[0].text
        assert "Page 2 of Sample PDF" in documents[0].text
        assert "Page 4 of Sample PDF" in documents[0].text

    @pytest.mark.integration
    @pytest.mark.skipif(
        "CORE_AZURE_CS_ENDPOINT" not in os.environ and "CORE_AZURE_CS_API_KEY" not in os.environ,
        reason="Azure credentials not available",
    )
    def test_with_image_file(self, preview_samples_path):
        component = AzureOCRDocumentConverter(
            endpoint=os.environ["CORE_AZURE_CS_ENDPOINT"], api_key=os.environ["CORE_AZURE_CS_API_KEY"]
        )
        output = component.run(paths=[preview_samples_path / "images" / "haystack-logo.png"])
        documents = output["documents"]
        assert len(documents) == 1
        assert "haystack" in documents[0].text
        assert "by deepset" in documents[0].text

    @pytest.mark.integration
    @pytest.mark.skipif(
        "CORE_AZURE_CS_ENDPOINT" not in os.environ and "CORE_AZURE_CS_API_KEY" not in os.environ,
        reason="Azure credentials not available",
    )
    def test_run_with_docx_file(self, preview_samples_path):
        component = AzureOCRDocumentConverter(
            endpoint=os.environ["CORE_AZURE_CS_ENDPOINT"], api_key=os.environ["CORE_AZURE_CS_API_KEY"]
        )
        output = component.run(paths=[preview_samples_path / "docx" / "sample_docx.docx"])
        documents = output["documents"]
        assert len(documents) == 1
        assert "Sample Docx File" in documents[0].text
        assert "Now we are in Page 2" in documents[0].text
        assert "Page 3 was empty this is page 4" in documents[0].text
