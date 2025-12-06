from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 17: Real-World Framework Patterns
# =============================================================================


class TestFrameworkPatterns:
    """Test patterns from real-world TypeScript frameworks."""

    def test_angular_component_pattern(self, tmp_path):
        """Must detect Angular component pattern."""
        test_file = tmp_path / "app.component.ts"
        test_file.write_text(
            """
@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
    styleUrls: ['./app.component.css']
})
export class AppComponent {
    title = 'my-app';

    ngOnInit() {
        console.log('Initialized');
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "AppComponent" in result["found_classes"]
        assert "ngOnInit" in result["found_methods"]["AppComponent"]

    def test_nestjs_controller_pattern(self, tmp_path):
        """Must detect NestJS controller pattern."""
        test_file = tmp_path / "users.controller.ts"
        test_file.write_text(
            """
@Controller('users')
export class UsersController {
    @Get()
    findAll() {
        return [];
    }

    @Post()
    create(@Body() createUserDto: CreateUserDto) {
        return {};
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "UsersController" in result["found_classes"]
        assert "findAll" in result["found_methods"]["UsersController"]
        assert "create" in result["found_methods"]["UsersController"]

    def test_vue_component_pattern(self, tmp_path):
        """Must detect Vue component pattern."""
        test_file = tmp_path / "MyComponent.vue.ts"
        test_file.write_text(
            """
@Component
export default class MyComponent extends Vue {
    private message: string = 'Hello';

    mounted() {
        console.log('Mounted');
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MyComponent" in result["found_classes"]
        assert "mounted" in result["found_methods"]["MyComponent"]
